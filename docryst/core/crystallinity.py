"""结晶度计算：面积比法 + 不确定度传播 + 质量诊断。

公式（相对质量结晶度 / degree of crystallinity）
------------------------------------------------
    C = Ac / (Ac + Aa) × 100 %

``Ac`` 为全部结晶峰（FWHM ≤ 判据）的积分面积之和，``Aa`` 为全部非晶宽包
（FWHM > 判据）的面积之和。两个面积都是 pseudo-Voigt 分量的**解析面积**，
不是数值积分——这一点在宽包上差别可达数个百分点（见 profile.py 说明）。

交叉验证（总面积法）
--------------------
    C_total = (A_obs − Aa) / A_obs × 100 %

``A_obs`` 为扣背景后观测谱的梯形积分。若拟合充分（覆盖度→1），两法应收敛到
同一数值；两者相差大，说明有未建模的强度（漏峰、背景口径不当、非晶包形状
不合适），此时以「拟合覆盖度」与 ``Rwp`` 判断可信度，而不是硬取某一个值。

不确定度
--------
C 是面积的比值，误差不能只取各峰面积误差的平方和（宽包与尖峰在拟合中高度
相关）。这里对面积向量 ``a`` 用完整协方差传播：

    g_i = ∂C/∂A_i = (1 − C)/(Ac+Aa)   （结晶峰）
                   = −C/(Ac+Aa)        （非晶峰）
    σ²(C) = gᵀ Σ_a g

``Σ_a`` 取自拟合协方差矩阵中面积参数的行列（锁定面积的峰方差记 0）。
"""

from __future__ import annotations

import numpy as np

from docryst.core import fitting as fitmod
from docryst.core.dtypes import (
    KIND_AMORPHOUS,
    KIND_CRYSTAL,
    BackgroundConfig,
    CrystResult,
    FitResult,
    Pattern,
    PeakResult,
    PeakSpec,
)
from docryst.core.peakfind import FindOptions, classify, find_peaks

# --------------------------------------------------------------------------- #
# 阈值常量（质量诊断）
# --------------------------------------------------------------------------- #
#: 拟合覆盖度低于此值提示"有未建模强度"
COVERAGE_WARN = 0.90
#: Rwp 高于此值提示拟合质量不佳
RWP_WARN = 0.15


def summarize(fit: FitResult, fwhm_threshold: float,
              do_classify: bool = True) -> CrystResult:
    """由拟合结果汇总结晶度（并回填峰表面积占比）。

    两种口径同时给出，避免"一个数字说不清"：

    * ``degree``（面积比法，主口径）用**解析面积**：pV 的积分为 ``area`` 恒等式，
      与拟合窗口无关。宽包峰尾即使延伸到窗口之外也被计入——非晶相不会因为
      扫描到 60° 就停止存在。因此同一模型下换窗口，C 值应基本不变。
    * ``degree_total``（总面积法，交叉验证）只用**窗口内**积分：观测谱扣背景后的
      面积 ``A_obs`` 与各分量在窗口内的梯形积分。它与主口径的差值正好反映
      "有多少宽包强度落在拟合窗口外"，是判断窗口是否够宽的指标，而非误差。
    """
    peaks = list(fit.peaks)
    if do_classify:
        peaks = classify(peaks, fwhm_threshold)

    area_c = sum(p.area for p in peaks if p.kind == KIND_CRYSTAL)
    area_a = sum(p.area for p in peaks if p.kind == KIND_AMORPHOUS)
    area_all = area_c + area_a
    degree = 100.0 * area_c / area_all if area_all > 0 else float("nan")

    x = np.asarray(fit.x, dtype=float)
    y_net = np.maximum(np.asarray(fit.y_obs, dtype=float) - fit.y_bg, 0.0)
    area_obs = float(np.trapezoid(y_net, x))

    # 窗口内积分（分量曲线逐条积分，负部截零）
    win_c = win_a = 0.0
    for comp, p in zip(fit.components, peaks):
        a_win = float(np.trapezoid(np.maximum(comp, 0.0), x))
        if p.kind == KIND_CRYSTAL:
            win_c += a_win
        else:
            win_a += a_win
    degree_total = (100.0 * (area_obs - win_a) / area_obs) if area_obs > 0 else float("nan")
    fit_win = win_c + win_a
    coverage = fit_win / area_obs if area_obs > 0 else float("nan")

    sigma = _sigma_degree(fit, peaks, area_c, area_a)
    peak_results = _peak_results(peaks, area_all)
    edge_ratio = _halo_edge_ratio(fit, peaks)
    warnings = _diagnose(peaks, fit, coverage, fwhm_threshold,
                         tail_leak=_tail_leak(area_a, win_a),
                         halo_edge=edge_ratio)

    return CrystResult(
        degree=degree,
        sigma=sigma,
        area_crystal=area_c,
        area_amorphous=area_a,
        n_crystal=sum(1 for p in peaks if p.kind == KIND_CRYSTAL),
        n_amorphous=sum(1 for p in peaks if p.kind == KIND_AMORPHOUS),
        area_obs_total=area_obs,
        degree_total=degree_total,
        coverage=coverage,
        fwhm_threshold=float(fwhm_threshold),
        halo_edge_ratio=edge_ratio,
        peaks=peak_results,
        rwp=fit.rwp,
        r2=fit.r2,
        fit=fit,
        warnings=warnings,
    )


def _peak_results(peaks: list[PeakSpec], total: float) -> list[PeakResult]:
    """峰表行（Jade 报告口径：2θ / d / 峰高 / 面积 / 面积% / FWHM / 判定）。"""
    rows: list[PeakResult] = []
    for i, p in enumerate(peaks):
        rows.append(PeakResult(
            index=i, pos=p.pos, fwhm=p.fwhm, area=p.area, eta=p.eta,
            kind=p.kind, area_err=p.area_err, pos_err=p.pos_err,
            fwhm_err=p.fwhm_err, height=p.height, label=p.label,
            total_area=total,
        ))
    return rows


def _sigma_degree(fit: FitResult, peaks: list[PeakSpec],
                  area_c: float, area_a: float) -> float:
    """按面积协方差传播 C 的 1σ（百分点）。无协方差时返回 0。"""
    total = area_c + area_a
    if fit.cov is None or total <= 0 or not np.isfinite(total):
        return 0.0
    idx = fit.free_index.get("area", {})
    n = len(peaks)
    if not idx:
        return 0.0
    grad = np.zeros(n)
    frac = area_c / total
    for i, p in enumerate(peaks):
        grad[i] = (1.0 - frac) if p.kind == KIND_CRYSTAL else -frac
        grad[i] /= total
    cov = fit.cov
    var = 0.0
    for i in range(n):
        vi = idx.get(i)
        if vi is None:
            continue
        for j in range(n):
            vj = idx.get(j)
            if vj is None:
                continue
            var += grad[i] * grad[j] * cov[vi, vj]
    return float(np.sqrt(max(var, 0.0)) * 100.0)


def _tail_leak(area_a_full: float, area_a_window: float) -> float:
    """非晶包"落在窗口外的面积比例"（0 表示宽包完整落在窗口内）。"""
    if area_a_full <= 0:
        return 0.0
    return float(max(0.0, 1.0 - area_a_window / area_a_full))


def _halo_edge_ratio(fit: FitResult, peaks: list[PeakSpec]) -> float:
    """非晶分量在**区间端点**的强度相对其峰顶的最大比例。

    该量直接决定"端点直线背景"的吃包程度：端点直线恒以两端强度为起点，
    非晶包在端点的强度会被整段当作背景扣掉。比例 >3% 即在结果卡提示。
    """
    ratio = 0.0
    for comp, p in zip(fit.components, peaks):
        if p.kind != KIND_AMORPHOUS or comp.size == 0:
            continue
        top = float(np.max(comp))
        if top <= 0:
            continue
        ratio = max(ratio, float(max(comp[0], comp[-1])) / top)
    return ratio


def _diagnose(peaks: list[PeakSpec], fit: FitResult, coverage: float,
              threshold: float, tail_leak: float = 0.0,
              halo_edge: float = 0.0) -> list[str]:
    """生成诊断提示（返回 i18n key 列表，由界面翻译）。"""
    keys: list[str] = []
    n_a = sum(1 for p in peaks if p.kind == KIND_AMORPHOUS)
    n_c = len(peaks) - n_a
    if not peaks:
        keys.append("warn.no_peaks")
        return keys
    if n_a == 0:
        keys.append("warn.no_amorphous")
    if n_c == 0:
        keys.append("warn.no_crystal")
    if np.isfinite(coverage) and coverage < COVERAGE_WARN:
        keys.append("warn.coverage")
    if np.isfinite(fit.rwp) and fit.rwp > RWP_WARN:
        keys.append("warn.rwp")
    if not fit.success:
        keys.append("warn.not_converged")
    if any(p.fwhm >= 59.0 for p in peaks):
        keys.append("warn.fwhm_bound")
    if any(abs(p.fwhm - threshold) < 0.25 * threshold for p in peaks) and n_a:
        keys.append("warn.threshold_near")
    if tail_leak > 0.15:
        keys.append("warn.halo_tail")
    if halo_edge > 0.03 and n_a:
        keys.append("warn.halo_edge")
    return keys


# --------------------------------------------------------------------------- #
# 一键自动分析 / 批量
# --------------------------------------------------------------------------- #
def auto_analyze(pattern: Pattern, cfg: BackgroundConfig, *,
                 lo: float | None = None, hi: float | None = None,
                 fwhm_threshold: float = 3.0,
                 find_opt: FindOptions | None = None,
                 fit_opt: fitmod.FitOptions | None = None,
                 peaks: list[PeakSpec] | None = None,
                 with_covariance: bool = True,
                 max_passes: int = 3) -> CrystResult:
    """自动流程：裁区间 → 扣背景 → 寻峰（或沿用给定峰）→ 全谱拟合 → 汇总。

    迭代补峰（``max_passes``）
    --------------------------
    一次寻峰常常漏掉被尖峰掩蔽的**宽非晶包**：非晶包在全局显著度上只有尖峰的
    百分之几，而"显著度"是相对全谱最高峰计算的，于是宽包被阈值挡在门外，
    其强度被尖峰拟合"吸走"（面积虚高、Rwp 虚差）。这里改为拟合—看残差—补峰
    的迭代：每轮在**残差**上找显著正结构（宽包在残差里非常显眼），补进峰表
    后整体重拟，直至无新峰或达到 ``max_passes``。

    ``peaks`` 给定时跳过寻峰（用于批量复用同一套峰位模板，或复算工程存档），
    此模式不做自动补峰——用户的峰表就是最终口径。
    """
    fit_opt = fit_opt or fitmod.FitOptions()
    if not with_covariance:
        fit_opt = fitmod.FitOptions(**{**fit_opt.__dict__, "with_covariance": False})

    pat = pattern
    if lo is not None or hi is not None:
        a, b = pattern.span
        pat = pattern.crop(lo if lo is not None else a, hi if hi is not None else b)

    x = pat.two_theta
    y = pat.intensity
    _bg, _comps, _calc = fitmod.model_curves(x, y, [], cfg)
    y_net = np.maximum(y - _bg, 0.0)

    user_peaks = peaks is not None
    if peaks is None:
        fopt = find_opt or FindOptions(fwhm_threshold=fwhm_threshold)
        peaks = find_peaks(x, y_net, fopt)
    if not peaks:
        # 无峰可拟合：返回空结果而不是抛异常（界面上提示"未检出峰，请手动加峰"）
        empty = FitResult(
            x=x, y_obs=y, y_calc=_bg, y_bg=_bg, components=[], peaks=[],
            bg_params=np.zeros(0), rwp=float("nan"), r2=float("nan"),
            chi2=float("nan"), n_iter=0, success=False,
            message="no-peak-found")
        return summarize(empty, fwhm_threshold, do_classify=False)

    fit = fitmod.fit(x, y, peaks, cfg, fit_opt)
    if not user_peaks:
        for _ in range(max(0, int(max_passes) - 1)):
            added = _residual_candidates(x, fit, fwhm_threshold)
            if added:
                peaks = _merge_peaks(list(fit.peaks), added)
                fit = fitmod.fit(x, y, peaks, cfg, fit_opt)
            # 拟合会放大宽分量的半高宽，"同一个非晶包被劈成两个"往往在拟合后
            # 才显现；此处做一次去重，若有删减则重拟一次收敛
            trimmed = _drop_split_amorphous(fit.peaks, fwhm_threshold)
            if len(trimmed) == len(fit.peaks):
                if not added:
                    break
                continue
            fit = fitmod.fit(x, y, trimmed, cfg, fit_opt)
    return summarize(fit, fwhm_threshold)


def _drop_split_amorphous(peaks: list[PeakSpec], fwhm_threshold: float) -> list[PeakSpec]:
    """若两个宽分量中心距小于较窄者 FWHM 的 0.75 倍，丢弃面积较小者。

    宽包被两个 pV 劈开时总残差可以更小，但面积分配失去物理意义（两半个包
    谁是"非晶"都说不清）。这里保留面积较大的主包，让它在重拟中吸收全部强度。
    用户若确实需要双峰非晶（如某些聚合物双驼峰），手动加峰并锁定类型即可
    （``kind_locked``），本函数只作用于自动流程。
    """
    broad = [(i, p) for i, p in enumerate(peaks) if p.fwhm > 0.5 * fwhm_threshold]
    drop: set[int] = set()
    for a in range(len(broad)):
        i, pi = broad[a]
        if i in drop:
            continue
        for b in range(a + 1, len(broad)):
            j, pj = broad[b]
            if j in drop:
                continue
            if abs(pi.pos - pj.pos) < 0.75 * min(pi.fwhm, pj.fwhm):
                drop.add(j if pi.area >= pj.area else i)
                if i in drop:
                    break
    if not drop:
        return list(peaks)
    return [p for i, p in enumerate(peaks) if i not in drop]


# --------------------------------------------------------------------------- #
# 迭代补峰
# --------------------------------------------------------------------------- #
#: 残差寻峰：显著度与峰高阈值（相对残差最大值）。取值偏保守——补峰只针对
#: "结构性的漏建模"，不追噪声。
RESID_PROMINENCE = 0.08
RESID_HEIGHT = 0.06
#: 残差峰值低于观测谱最大强度的此比例时不再补峰（避免越拟合越碎）
RESID_MIN_FRAC = 0.01


def _residual_candidates(x: np.ndarray, fit: FitResult,
                         fwhm_threshold: float) -> list[PeakSpec]:
    """在残差上找"尚未被建模"的显著分量。"""
    resid = np.asarray(fit.y_obs, dtype=float) - np.asarray(fit.y_calc, dtype=float)
    pos_part = np.maximum(resid, 0.0)
    peak = float(pos_part.max()) if pos_part.size else 0.0
    scale = float(np.max(fit.y_obs)) if np.size(fit.y_obs) else 0.0
    if peak <= 0 or peak < RESID_MIN_FRAC * max(scale, 1.0):
        return []
    opt = FindOptions(
        prominence_frac=RESID_PROMINENCE, height_frac=RESID_HEIGHT,
        min_distance_deg=0.15, max_peaks=4, fwhm_threshold=fwhm_threshold,
        min_area_frac=0.0,
    )
    cands = find_peaks(x, pos_part, opt)
    return [c for c in cands if _is_far_enough(c, fit.peaks, fwhm_threshold)]


def _is_far_enough(cand: PeakSpec, peaks: list[PeakSpec],
                   fwhm_threshold: float) -> bool:
    """候选峰是否应被接纳（防重复与防"一个宽包被劈成两个"）。

    两条判据：
    * 两个**宽分量**（任一 FWHM 超过判据的一半）中心距小于较窄者 FWHM 的
      0.75 倍时视为同一个非晶包的重复建模，拒绝——这是本工具最需要防的
      伪解：一个宽包被两个 pV 劈开时，总拟合残差可以更小，但面积分配失去
      物理意义（残差寻峰阶段尤其容易发生）。
    * 其余情形按中心距 < max(0.12°, 0.5×较窄 FWHM) 去重（同一尖峰被重复检出）。
    """
    for p in peaks:
        gap = abs(cand.pos - p.pos)
        both_broad = (cand.fwhm > 0.5 * fwhm_threshold
                      and p.fwhm > 0.5 * fwhm_threshold)
        if both_broad:
            if gap < 0.75 * min(cand.fwhm, p.fwhm):
                return False
        elif gap < max(0.12, 0.5 * min(cand.fwhm, p.fwhm)):
            return False
    return True


def _merge_peaks(peaks: list[PeakSpec], added: list[PeakSpec]) -> list[PeakSpec]:
    """合并峰表并按 2θ 升序（峰类型保持原样，分类在拟合后统一做）。"""
    return sorted(list(peaks) + list(added), key=lambda p: p.pos)
