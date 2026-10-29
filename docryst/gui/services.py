"""GUI ↔ core 的唯一通道：读谱、分析、拟合的封装。

家族约定：GUI 不直接 import core 的算法细节，一律经本模块，
便于单元测试（offscreen 冒烟）与后续批处理复用。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from docryst.core.crystallinity import auto_analyze, summarize
from docryst.core.dtypes import (
    CU_KA1,
    BackgroundConfig,
    CrystResult,
    Pattern,
    PeakSpec,
)
from docryst.core import fitting as fitmod
from docryst.core.peakfind import FindOptions
from docryst.core.vendor.text_formats import load_pattern as vendor_load

__all__ = [
    "AnalysisParams", "load_pattern", "run_auto", "run_fit", "preview_curves",
    "new_peak_at", "freeze_all_but", "pattern_ext_filter",
]


# --------------------------------------------------------------------------- #
# 参数束
# --------------------------------------------------------------------------- #
class AnalysisParams:
    """一次分析的全部可调参数（面板 → worker 的传递载体）。"""

    def __init__(self, *, lo: float | None = None, hi: float | None = None,
                 bg_cfg: BackgroundConfig | None = None,
                 fwhm_threshold: float = 3.0,
                 fit_opt: fitmod.FitOptions | None = None,
                 find_opt: FindOptions | None = None,
                 peaks: list[PeakSpec] | None = None,
                 auto_add_peaks: bool = True) -> None:
        self.lo = lo
        self.hi = hi
        self.bg_cfg = bg_cfg or BackgroundConfig()
        self.fwhm_threshold = fwhm_threshold
        self.fit_opt = fit_opt or fitmod.FitOptions()
        self.find_opt = find_opt or FindOptions(fwhm_threshold=fwhm_threshold)
        self.peaks = list(peaks) if peaks is not None else None
        self.auto_add_peaks = auto_add_peaks


# --------------------------------------------------------------------------- #
# 读谱
# --------------------------------------------------------------------------- #
def load_pattern(path: str | Path) -> Pattern:
    """读取谱图并规范化为 :class:`Pattern`（2θ 升序、Kα1 波长缺省 Cu）。"""
    raw = vendor_load(str(path))
    tt = np.asarray(raw.two_theta, dtype=float)
    yy = np.asarray(raw.intensity, dtype=float)
    order = np.argsort(tt)
    tt, yy = tt[order], yy[order]
    good = np.isfinite(tt) & np.isfinite(yy)
    tt, yy = tt[good], yy[good]
    wl = raw.wavelength or CU_KA1
    meta = dict(getattr(raw, "metadata", {}) or {})
    return Pattern(tt, yy, wavelength=float(wl), source=str(path), meta=meta)


#: 文件对话框扩展名（与 vendor 读谱器支持面一致）
PATTERN_EXTS = (
    ".xy", ".txt", ".dat", ".csv", ".raw", ".org", ".rsm", ".rbg",
    ".rk1", ".rax", ".rlz", ".rfi", ".mdi", ".gsas", ".gss", ".gsa",
    ".gda", ".fxye", ".ras", ".rasx", ".xye", ".qye", ".chi", ".qchi",
    ".xrdml", ".xml", ".brml", ".json", ".smz",
)


#: 文件对话框过滤器（与家族口径一致）
def pattern_ext_filter() -> str:
    patterns = " ".join(f"*{e}" for e in PATTERN_EXTS)
    return f"XRD Patterns ({patterns});;All Files (*.*)"


# --------------------------------------------------------------------------- #
# 分析
# --------------------------------------------------------------------------- #
def run_auto(pattern: Pattern, params: AnalysisParams) -> CrystResult:
    """自动分析（寻峰 + 迭代补峰 + 全谱拟合 + 汇总），worker 线程调用。"""
    return auto_analyze(
        pattern, params.bg_cfg, lo=params.lo, hi=params.hi,
        fwhm_threshold=params.fwhm_threshold, find_opt=params.find_opt,
        fit_opt=params.fit_opt, peaks=params.peaks,
        max_passes=3 if params.auto_add_peaks else 1)


def run_fit(pattern: Pattern, params: AnalysisParams) -> CrystResult:
    """按给定峰表拟合（不寻峰），worker 线程调用。"""
    pat = pattern
    if params.lo is not None or params.hi is not None:
        a, b = pattern.span
        pat = pattern.crop(params.lo if params.lo is not None else a,
                           params.hi if params.hi is not None else b)
    fit = fitmod.fit(pat.two_theta, pat.intensity,
                     list(params.peaks or []), params.bg_cfg, params.fit_opt)
    return summarize(fit, params.fwhm_threshold)


def preview_curves(pattern: Pattern, params: AnalysisParams):
    """不拟合，直接按当前峰参数求值（拖动峰位时的实时预览）。

    返回 (x, y_obs, y_bg, components, y_calc)。
    """
    pat = pattern
    if params.lo is not None or params.hi is not None:
        a, b = pattern.span
        pat = pattern.crop(params.lo if params.lo is not None else a,
                           params.hi if params.hi is not None else b)
    y_bg, comps, y_calc = fitmod.model_curves(
        pat.two_theta, pat.intensity, list(params.peaks or []),
        params.bg_cfg, None)
    return pat.two_theta, pat.intensity, y_bg, comps, y_calc


# --------------------------------------------------------------------------- #
# 峰操作（供画布与峰表共用）
# --------------------------------------------------------------------------- #
def new_peak_at(x: np.ndarray, y_net: np.ndarray, pos: float,
                fwhm_threshold: float = 3.0) -> PeakSpec:
    """在点击位置构造初值峰（FWHM 超判据则直接判为非晶）。"""
    return fitmod.new_peak_at(x, y_net, pos)


def freeze_all_but(peaks: list[PeakSpec], keep: list[int]) -> list[PeakSpec]:
    return fitmod.freeze_all_but(peaks, keep)
