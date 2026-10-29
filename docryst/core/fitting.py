"""全局最小二乘分峰拟合（背景 + 全部峰分量同时优化）。

模型
----
    y_calc(x) = bg(x) + Σ_j pV_j(x; pos_j, fwhm_j, area_j, η_j)

其中背景 ``bg`` 可固定（两端点直线 / 手动锚点 / SNIP）也可自由（直线 / 多项式，
参数进入同一个参数向量）。求解用 ``scipy.optimize.least_squares``（TRF，带界），
不用 LM：界约束能让"峰位跑出区间""半高宽变负"这类病态解直接不可达。

权重与指标
----------
* 默认 Poisson 权重 ``σ = √max(y, 1)``（计数统计下的近似标准差）；
* ``Rwp = √( Σw(y_obs−y_calc)² / Σw·y_obs² )``，与 Rietveld 的 Rwp 同式，
  便于与 RutAna 的 B 法结果横向比较（量级意义一致，不是同一模型）；
* ``R² = 1 − SSres/SStot``（对 y_obs 均值的总平方和）；
* 参数标准偏差由协方差 ``Cov = (JᵀJ)⁻¹·s²`` 给出，``s² = 2·cost/dof``，
  即用残差方差重标定（不假定噪声真服从 Poisson）。

锁定语义
--------
``PeakSpec.fix_pos/fix_fwhm/fix_area`` 为 True 的参数不进优化向量——这就是
「手动拟合」的控制手段：先自动拟合，再把满意的峰锁死，只放开需要调的那个。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

import numpy as np
from scipy.optimize import least_squares

from docryst.core import background as bgmod
from docryst.core.dtypes import BackgroundConfig, FitResult, PeakSpec
from docryst.core.profile import pv_height, pseudo_voigt

__all__ = ["FitOptions", "fit", "model_curves", "freeze_all_but", "new_peak_at"]

#: 面积上界（数值保护，避免 TRF 在无界方向的病态探索）
AREA_MAX = 1e15


@dataclass
class FitOptions:
    """拟合选项。"""

    fit_background: bool = True
    #: 是否让 η（洛伦兹占比）参与优化
    free_eta: bool = True
    #: 所有峰共用一个 η（峰形统一，参数更少更稳）
    tie_eta: bool = False
    #: 稳健损失（soft_l1）：对个别强峰尖的离群点不敏感，但协方差仅近似
    robust: bool = False
    #: 权重口径："poisson" | "uniform"
    weight: str = "poisson"
    max_nfev: int = 600
    #: 估计参数协方差（关掉可提速，批量时用）
    with_covariance: bool = True
    min_fwhm: float = 0.02
    max_fwhm: float = 60.0


# --------------------------------------------------------------------------- #
# 模型求值
# --------------------------------------------------------------------------- #
def model_curves(x: np.ndarray, y_for_bg: np.ndarray, peaks: list[PeakSpec],
                 cfg: BackgroundConfig, bg_params: np.ndarray | None = None
                 ) -> tuple[np.ndarray, list[np.ndarray], np.ndarray]:
    """返回 (背景曲线, 各峰分量, 合计曲线)。画布预览与拟合内部共用。"""
    x = np.asarray(x, dtype=float)
    y_bg = bgmod.evaluate(x, y_for_bg, cfg, bg_params)
    comps = [pseudo_voigt(x, p.pos, p.fwhm, p.area, p.eta) for p in peaks]
    y_calc = y_bg
    for c in comps:
        y_calc = y_calc + c
    return y_bg, comps, y_calc


# --------------------------------------------------------------------------- #
# 参数向量布局
# --------------------------------------------------------------------------- #
class _Layout:
    """自由参数向量 ↔ 峰/背景字段的映射。"""

    def __init__(self, peaks: list[PeakSpec], opt: FitOptions, cfg: BackgroundConfig,
                 x: np.ndarray, y: np.ndarray) -> None:
        self.entries: list[tuple[str, int]] = []      # ("pos"/"fwhm"/"area"/"eta", peak_idx)
        self.x0: list[float] = []
        self.lo: list[float] = []
        self.hi: list[float] = []
        self.index: dict[str, dict[int, int]] = {"pos": {}, "fwhm": {}, "area": {}, "eta": {}}

        x_lo, x_hi = float(x[0]), float(x[-1])
        span = max(1e-6, x_hi - x_lo)

        for i, p in enumerate(peaks):
            if not p.fix_pos:
                self._add("pos", i, min(max(p.pos, x_lo), x_hi), x_lo - 0.02 * span,
                          x_hi + 0.02 * span)
            if not p.fix_fwhm:
                f0 = float(np.clip(p.fwhm, opt.min_fwhm, opt.max_fwhm))
                self._add("fwhm", i, f0, opt.min_fwhm, opt.max_fwhm)
            if not p.fix_area:
                a0 = float(max(p.area, 1e-9))
                self._add("area", i, a0, 0.0, AREA_MAX)
            if opt.free_eta and not opt.tie_eta:
                self._add("eta", i, float(np.clip(p.eta, 0.0, 1.0)), 0.0, 1.0)
        if opt.free_eta and opt.tie_eta and peaks:
            self._add("eta", -1, float(np.clip(peaks[0].eta, 0.0, 1.0)), 0.0, 1.0)

        self.bg_offset = len(self.entries)
        if opt.fit_background and cfg.is_free():
            n_bg = cfg.n_params()
            p0 = bgmod.default_free_params(x, y, cfg)
            lo_b, hi_b = bgmod.bounds_free(x, y, cfg)
            for k in range(n_bg):
                self.entries.append(("bg", k))
                self.x0.append(float(p0[k]))
                self.lo.append(float(lo_b[k]))
                self.hi.append(float(hi_b[k]))

    def _add(self, name: str, peak_idx: int, v0: float, lo: float, hi: float) -> None:
        self.index[name][peak_idx] = len(self.entries)
        self.entries.append((name, peak_idx))
        self.x0.append(float(v0))
        self.lo.append(float(lo))
        self.hi.append(float(hi))

    @property
    def size(self) -> int:
        return len(self.entries)

    def unpack(self, vec: np.ndarray, template: list[PeakSpec],
               cfg: BackgroundConfig) -> tuple[list[PeakSpec], np.ndarray | None]:
        """把参数向量还原为峰列表与背景参数向量。"""
        vals = {name: {} for name in ("pos", "fwhm", "area", "eta")}
        bg_vals: list[float] = []
        for pos_idx, (name, sub) in enumerate(self.entries):
            if name == "bg":
                bg_vals.append(float(vec[pos_idx]))
            else:
                vals[name][sub] = float(vec[pos_idx])
        peaks = []
        eta_all = vals["eta"].get(-1)
        for i, p in enumerate(template):
            eta = vals["eta"].get(i, eta_all if eta_all is not None else p.eta)
            peaks.append(p.copy(
                pos=vals["pos"].get(i, p.pos),
                fwhm=vals["fwhm"].get(i, p.fwhm),
                area=vals["area"].get(i, p.area),
                eta=eta,
            ))
        bg_params = np.asarray(bg_vals, dtype=float) if bg_vals else None
        return peaks, bg_params


# --------------------------------------------------------------------------- #
# 主过程
# --------------------------------------------------------------------------- #
def fit(x: np.ndarray, y: np.ndarray, peaks: list[PeakSpec], cfg: BackgroundConfig,
        opt: FitOptions | None = None) -> FitResult:
    """对 ``(x, y)`` 做全谱分峰拟合，返回 :class:`FitResult`。

    ``peaks`` 中 ``fix_*`` 为 True 的参数不参与优化，其值原样保留在结果里。
    异常（奇异矩阵、求解器报错）不抛出——以 ``success=False`` 返回，界面据此
    提示"拟合未收敛"，避免把病态解当成结果。
    """
    opt = opt or FitOptions()
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    t0 = time.perf_counter()

    sigma = _sigma(y, opt.weight)
    layout = _Layout(peaks, opt, cfg, x, y)

    def _residual(vec: np.ndarray) -> np.ndarray:
        cur_peaks, cur_bg = layout.unpack(vec, peaks, cfg)
        _bg, _comps, y_calc = model_curves(x, y, cur_peaks, cfg, cur_bg)
        return (y_calc - y) / sigma

    if layout.size == 0 or not peaks:
        # 无自由参数：直接按当前参数求值（仍返回完整指标，供质量监控）
        bg_params = bgmod.default_free_params(x, y, cfg) if cfg.is_free() else None
        y_bg, comps, y_calc = model_curves(x, y, peaks, cfg, bg_params)
        return _pack_result(x, y, y_bg, comps, y_calc, list(peaks), bg_params,
                            np.zeros(0), 0, True, "no-free-parameter", None,
                            layout.index, cfg, opt, t0)

    x0 = np.asarray(layout.x0, dtype=float)
    lo = np.asarray(layout.lo, dtype=float)
    hi = np.asarray(layout.hi, dtype=float)
    # 初值必须严格落在界内，否则 TRF 直接报错
    x0 = np.clip(x0, lo + 1e-12 * np.maximum(1.0, np.abs(lo)), hi - 1e-12 * np.maximum(1.0, np.abs(hi)))

    try:
        res = least_squares(
            _residual, x0, bounds=(lo, hi), method="trf",
            loss="soft_l1" if opt.robust else "linear",
            max_nfev=int(opt.max_nfev), xtol=1e-10, ftol=1e-10, gtol=1e-10,
            x_scale="jac",
        )
        vec = res.x
        success = bool(res.success or res.status > 0)
        message = str(res.message)
        jac = res.jac
        cost = float(res.cost)
        nfev = int(res.nfev)
    except Exception as exc:  # noqa: BLE001 —— 求解器异常一律降级为"未收敛"
        vec = x0
        success = False
        message = f"{type(exc).__name__}: {exc}"
        jac = None
        cost = float("nan")
        nfev = 0

    cur_peaks, bg_params = layout.unpack(vec, peaks, cfg)
    y_bg, comps, y_calc = model_curves(x, y, cur_peaks, cfg, bg_params)

    cov = None
    if opt.with_covariance and jac is not None:
        cov = _covariance(jac, cost, x.size, layout.size, opt.robust)

    result = _pack_result(x, y, y_bg, comps, y_calc, cur_peaks, bg_params, vec,
                          nfev, success, message, cov, layout.index, cfg, opt, t0)
    return result


def _pack_result(x, y, y_bg, comps, y_calc, peaks, bg_params, vec, nfev,
                 success, message, cov, free_index, cfg, opt, t0) -> FitResult:
    """计算质量指标并组装 :class:`FitResult`（并把参数误差写回峰表）。"""
    sigma = _sigma(y, opt.weight)
    resid = y - y_calc
    w = 1.0 / sigma ** 2
    sw = float(np.sum(w * y ** 2))
    rwp = float(np.sqrt(np.sum(w * resid ** 2) / sw)) if sw > 0 else float("nan")
    sstot = float(np.sum((y - np.mean(y)) ** 2))
    ssres = float(np.sum(resid ** 2))
    r2 = float(1.0 - ssres / sstot) if sstot > 0 else float("nan")
    dof = max(1, x.size - len(vec))
    chi2 = float(ssres / dof)

    if cov is not None and vec.size:
        errs = np.sqrt(np.clip(np.diag(cov), 0.0, None))
        for name in ("pos", "fwhm", "area"):
            for pi, vi in free_index.get(name, {}).items():
                if 0 <= pi < len(peaks) and vi < errs.size:
                    setattr(peaks[pi], f"{name}_err", float(errs[vi]))

    return FitResult(
        x=x, y_obs=y, y_calc=y_calc, y_bg=y_bg, components=comps, peaks=peaks,
        bg_params=bg_params if bg_params is not None else np.zeros(0),
        rwp=rwp, r2=r2, chi2=chi2, n_iter=nfev, success=success, message=message,
        cov=cov, free_index=free_index, elapsed_s=time.perf_counter() - t0,
    )


def _sigma(y: np.ndarray, weight: str) -> np.ndarray:
    if weight == "poisson":
        return np.sqrt(np.maximum(y, 1.0))
    return np.ones_like(y, dtype=float)


def _covariance(jac: np.ndarray, cost: float, n_data: int, n_par: int,
                robust: bool) -> np.ndarray | None:
    """参数协方差 ``(JᵀJ)⁻¹·s²``；奇异时用伪逆，仍失败返回 None。"""
    if jac is None or n_par == 0:
        return None
    dof = n_data - n_par
    if dof <= 0:
        return None
    s2 = (2.0 * cost) / dof if np.isfinite(cost) else 1.0
    jtj = jac.T @ jac
    try:
        inv = np.linalg.inv(jtj)
    except np.linalg.LinAlgError:
        try:
            inv = np.linalg.pinv(jtj)
        except np.linalg.LinAlgError:
            return None
    cov = inv * max(s2, 1e-30)
    if robust:
        # soft_l1 的 J 不含稳健重加权项，方差会被低估；此处不做虚高修正，
        # 仅在结果卡上提示"稳健损失下误差为近似值"。
        pass
    return cov


# --------------------------------------------------------------------------- #
# 便捷操作
# --------------------------------------------------------------------------- #
def freeze_all_but(peaks: list[PeakSpec], keep: list[int]) -> list[PeakSpec]:
    """锁定除 ``keep`` 之外所有峰的参数（"只拟合选中峰"用）。"""
    keep_set = set(keep)
    out: list[PeakSpec] = []
    for i, p in enumerate(peaks):
        if i in keep_set:
            out.append(p.copy(fix_pos=False, fix_fwhm=False, fix_area=False))
        else:
            out.append(p.copy(fix_pos=True, fix_fwhm=True, fix_area=True))
    return out


def new_peak_at(x: np.ndarray, y_net: np.ndarray, pos: float,
                eta: float = 0.6, min_fwhm: float = 0.08) -> PeakSpec:
    """在用户点击的 2θ 位置构造一个合理初值的峰（面积/半高宽由局部数据估）。

    取点击点最近采样点为峰位；沿两侧找半高交点得 FWHM（若点击处不在峰顶，
    用局部最大值修正峰位）；面积取 ±1.2×FWHM 区间的净积分。
    """
    x = np.asarray(x, dtype=float)
    y_net = np.maximum(np.asarray(y_net, dtype=float), 0.0)
    i = int(np.argmin(np.abs(x - pos)))
    # 在 ±0.6° 内找局部极大，避免用户点在峰肩上导致初值偏离
    win = np.abs(x - x[i]) <= 0.6
    if np.any(win):
        idx_local = np.where(win)[0]
        i = int(idx_local[int(np.argmax(y_net[idx_local]))])
    fwhm = max(float(min_fwhm), _local_fwhm(x, y_net, i))
    # 面积初值：峰高 × FWHM（pV 的面积≈峰高×FWHM 的量级），下界给 1e-9
    area = float(max(y_net[i] * fwhm, 1e-9))
    return PeakSpec(pos=float(x[i]), fwhm=fwhm, area=area, eta=eta)


def _local_fwhm(x: np.ndarray, y: np.ndarray, i: int) -> float:
    """局部半高宽（找不到半高点时按 0.3° 兜底）。"""
    top = float(y[i])
    if top <= 0:
        return 0.3
    half = 0.5 * top
    left = x[0]
    for k in range(i, 0, -1):
        if y[k] <= half:
            left = float(x[k])
            break
    right = x[-1]
    for k in range(i, y.size - 1):
        if y[k] <= half:
            right = float(x[k])
            break
    return float(max(0.3, right - left))
