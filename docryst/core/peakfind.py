"""自动寻峰 + 半高宽估计 + 结晶/非晶初判。

自动寻峰只是**初值生成器**：结晶度分析的分峰结果最终由用户确认。因此这里的
策略是"宁可多找、不轻易漏掉宽包"，再由用户删峰或改判，而不是追求峰表最短。

算法
----
1. 扣背景后取正部（``y − bg``，负值截零）；
2. Savitzky-Golay 轻度平滑（窗口自适应 ≈ 谱点数的 1/400，强制奇数）；
3. ``scipy.signal.find_peaks``：用 prominence（相对最大净强度的比例）控制
   显著性，用 ``min_distance_deg`` 抑制同一个峰被重复检出；
4. 对每个候选峰回到**未平滑**的净信号，用半高法估计 FWHM、用局部积分估计面积；
5. 按峰高降序截断到 ``max_peaks``，再按 2θ 升序返回；
6. FWHM > ``fwhm_threshold`` 判为非晶宽包初判。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks as _find_peaks
from scipy.signal import savgol_filter

from docryst.core.dtypes import KIND_AMORPHOUS, KIND_CRYSTAL, PeakSpec
from docryst.core.profile import estimate_fwhm, segment_area


@dataclass
class FindOptions:
    """自动寻峰参数（界面上暴露为「灵敏度 / 最小间距 / 最大峰数」）。"""

    #: 显著度阈值（相对净信号最大值）：越小越灵敏
    prominence_frac: float = 0.02
    #: 峰高阈值（相对净信号最大值）
    height_frac: float = 0.01
    #: 两个候选峰的最小 2θ 间距（度）
    min_distance_deg: float = 0.12
    #: 平滑窗口（采样点数，0=自适应）
    smooth_window: int = 0
    #: 最多保留多少个峰（按峰高取舍）
    max_peaks: int = 24
    #: 非晶判据：FWHM 大于此值（度）初判为非晶
    fwhm_threshold: float = 3.0
    #: 峰面积下限（相对净信号总面积的百分比），滤掉噪声毛刺
    min_area_frac: float = 0.002


def _auto_window(n: int) -> int:
    """自适应平滑窗口：约 n/400，限制在 [5, 31]，强制奇数。"""
    w = int(max(5, min(31, round(n / 400.0))))
    return w if w % 2 == 1 else w + 1


def find_peaks(x: np.ndarray, y_net: np.ndarray,
               opt: FindOptions | None = None) -> list[PeakSpec]:
    """在**已扣背景**的信号上自动寻峰，返回按 2θ 升序的峰列表。"""
    opt = opt or FindOptions()
    x = np.asarray(x, dtype=float)
    net = np.maximum(np.asarray(y_net, dtype=float), 0.0)
    if x.size < 7 or not np.any(net > 0):
        return []

    top = float(net.max())
    if top <= 0:
        return []

    w = opt.smooth_window if opt.smooth_window and opt.smooth_window > 2 else _auto_window(x.size)
    if w % 2 == 0:
        w += 1
    w = min(w, x.size if x.size % 2 == 1 else x.size - 1)
    sm = savgol_filter(net, window_length=int(w), polyorder=2) if w >= 5 else net

    step = float(np.mean(np.diff(x)))
    distance = max(1, int(round(opt.min_distance_deg / step))) if step > 0 else 1

    idx, _props = _find_peaks(
        sm,
        prominence=opt.prominence_frac * top,
        height=opt.height_frac * top,
        distance=distance,
    )
    if idx.size == 0:
        return []

    total_net = float(np.trapezoid(net, x)) or 1.0
    cands: list[tuple[float, PeakSpec]] = []
    for i in idx:
        i = int(i)
        fwhm = estimate_fwhm(x, net, i, baseline=0.0)
        area = segment_area(x, net, i)
        if area <= 0 or area / total_net < opt.min_area_frac:
            continue
        kind = KIND_AMORPHOUS if fwhm > opt.fwhm_threshold else KIND_CRYSTAL
        cands.append((float(sm[i]), PeakSpec(pos=float(x[i]), fwhm=fwhm,
                                             area=area, kind=kind)))

    cands.sort(key=lambda item: item[0], reverse=True)
    cands = cands[: max(1, int(opt.max_peaks))]
    return sorted((spec for _h, spec in cands), key=lambda p: p.pos)


def classify(peaks: list[PeakSpec], fwhm_threshold: float) -> list[PeakSpec]:
    """按 FWHM 判据重判峰类型（返回新列表，不改动入参）。

    ``kind_locked=True`` 的峰保持用户手动改判的类型不变——自动判据只作用于
    用户尚未表态的峰，避免"一键重判"覆盖人工判断。
    """
    out: list[PeakSpec] = []
    for p in peaks:
        if p.kind_locked:
            out.append(p)
            continue
        kind = KIND_AMORPHOUS if p.fwhm > float(fwhm_threshold) else KIND_CRYSTAL
        out.append(p.copy(kind=kind))
    return out


def count_by_kind(peaks: list[PeakSpec]) -> tuple[int, int]:
    """返回 (结晶峰数, 非晶峰数)。"""
    n_a = sum(1 for p in peaks if p.kind == KIND_AMORPHOUS)
    return len(peaks) - n_a, n_a
