"""核心算法包（无 Qt / 无 matplotlib 依赖，可独立测试与批处理）。

典型用法::

    from docryst.core import BackgroundConfig, Pattern, auto_analyze

    pat = load_pattern("sample.xy")          # docryst.core.vendor.text_formats
    cfg = BackgroundConfig(model="linear_ends")
    res = auto_analyze(pat, cfg, fwhm_threshold=3.0)
    print(res.degree, res.sigma, res.n_crystal, res.n_amorphous)
"""

from __future__ import annotations

from docryst.core.crystallinity import auto_analyze, summarize
from docryst.core.dtypes import (
    DEFAULT_FWHM_AMORPH,
    KIND_AMORPHOUS,
    KIND_CRYSTAL,
    BackgroundConfig,
    CrystResult,
    FitResult,
    Pattern,
    PeakResult,
    PeakSpec,
)

__all__ = [
    "DEFAULT_FWHM_AMORPH", "KIND_AMORPHOUS", "KIND_CRYSTAL",
    "BackgroundConfig", "CrystResult", "FitResult", "Pattern", "PeakResult",
    "PeakSpec", "auto_analyze", "summarize",
]
