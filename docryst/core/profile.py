"""峰形：面积归一的 pseudo-Voigt（pV）及其派生量。

为什么用「面积参数化」
----------------------
常规 pV 用**峰高**参数化（``y = h·[ηL + (1-η)G]``），面积需按 η 与 FWHM 反算，
解析式虽存在但易与"半高宽"定义混淆；结晶度的公式恰恰只用面积。本实现把
幅值直接定义为积分面积，于是：

    ∫ pV(x) dx ≡ area          （解析恒等，不依赖数值积分截断）

这对**宽非晶包**尤其重要：其峰尾延伸到拟合区间之外，数值积分会系统性少算，
而宽包又恰是分母中的主体，误差会直接进入结晶度。用解析面积可完全避免。

pV 定义（Γ = FWHM）
-------------------
    G(x) = (2/Γ)·√(ln2/π)·exp(−4ln2·(x−x₀)²/Γ²)      高斯，积分为 1
    L(x) = (2/(πΓ)) / (1 + 4(x−x₀)²/Γ²)              洛伦兹，积分为 1
    pV(x) = area · [η·L(x) + (1−η)·G(x)]              η ∈ [0, 1]

η=0 纯高斯（更接近仪器展宽主导的小晶粒峰），η=1 纯洛伦兹（更接近宽包与
缺陷展宽）。Jade 的 PSF「仿 Voigt」即为此式，差别仅在其幅值用峰高。
"""

from __future__ import annotations

import numpy as np

_SQRT_LN2_PI = float(np.sqrt(np.log(2.0) / np.pi))
_TWO_SQRT_LN2_PI = 2.0 * _SQRT_LN2_PI


def pseudo_voigt(x: np.ndarray, pos: float, fwhm: float, area: float,
                 eta: float) -> np.ndarray:
    """面积归一 pseudo-Voigt 在 ``x`` 上的取值。"""
    x = np.asarray(x, dtype=float)
    g = float(max(fwhm, 1e-6))
    dx = x - float(pos)
    u = 2.0 * dx / g
    gauss = (_TWO_SQRT_LN2_PI / g) * np.exp(-np.log(2.0) * u * u)
    lorentz = (2.0 / (np.pi * g)) / (1.0 + u * u)
    e = float(min(max(eta, 0.0), 1.0))
    return float(area) * (e * lorentz + (1.0 - e) * gauss)


def pv_height(fwhm: float, area: float, eta: float) -> float:
    """峰顶高度（x = pos 处的值），由面积反算。"""
    if fwhm <= 0:
        return 0.0
    gauss = _TWO_SQRT_LN2_PI / fwhm
    lorentz = 2.0 / (np.pi * fwhm)
    return float(area * (eta * lorentz + (1.0 - eta) * gauss))


def pv_area_from_height(fwhm: float, height: float, eta: float) -> float:
    """由峰高反算面积（供手动加峰时以峰高为直观输入）。"""
    if fwhm <= 0:
        return 0.0
    gauss = _TWO_SQRT_LN2_PI / fwhm
    lorentz = 2.0 / (np.pi * fwhm)
    shape = eta * lorentz + (1.0 - eta) * gauss
    if shape <= 0:
        return 0.0
    return float(height / shape)


def pv_fwhm_from_area_height(area: float, height: float, eta: float) -> float:
    """由面积与峰高反算 FWHM（手动改峰高时保持面积口径自洽）。"""
    if height <= 0 or area <= 0:
        return 0.0
    shape = area / height            # = 1/(η·L₀ + (1−η)·G₀) 的 FWHM 倍率
    gauss = _TWO_SQRT_LN2_PI
    lorentz = 2.0 / np.pi
    coef = eta * lorentz + (1.0 - eta) * gauss
    return float(shape * coef) if coef > 0 else 0.0


def integrate_positive(x: np.ndarray, y: np.ndarray) -> float:
    """梯形积分（负值截零），用于观测谱总面积这类无法解析求积的量。"""
    yy = np.maximum(np.asarray(y, dtype=float), 0.0)
    return float(np.trapezoid(yy, np.asarray(x, dtype=float)))


def estimate_fwhm(x: np.ndarray, y: np.ndarray, idx: int,
                  baseline: float = 0.0) -> float:
    """在已扣背景的曲线上，以半高法估计 ``idx`` 处峰的 FWHM（度）。

    从峰顶向两侧逐点下降找半高交点（线性内插），两侧各取一半；若某一侧在
    区间内未降到半高（峰尾被截断或与邻峰重叠），以该侧可见宽度×2 近似并
    由调用方决定是否保留。找不到半高点时退化为 3 个步长。
    """
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    n = y.size
    if not (0 <= idx < n):
        return float(3.0 * np.mean(np.diff(x)) if n > 1 else 0.1)
    top = y[idx] - baseline
    if top <= 0:
        return float(3.0 * np.mean(np.diff(x)))
    half = baseline + 0.5 * top

    def _walk(step: int) -> float | None:
        i = idx
        prev = y[i]
        while 0 <= i + step < n:
            i += step
            cur = y[i]
            if cur <= half:
                # 在 prev 与 cur 之间线性内插半高点
                span = prev - cur
                frac = 0.0 if span <= 0 else (prev - half) / span
                return float(x[i - step] + frac * (x[i] - x[i - step]))
            prev = cur
        return None

    left = _walk(-1)
    right = _walk(+1)
    step = float(np.mean(np.diff(x)))
    if left is None and right is None:
        return float(3.0 * step)
    if left is None:
        return float(max(2.0 * (right - x[idx]), 3.0 * step))
    if right is None:
        return float(max(2.0 * (x[idx] - left), 3.0 * step))
    return float(right - left)


def segment_area(x: np.ndarray, y: np.ndarray, idx: int) -> float:
    """以峰位为中心、按半宽边界估算该峰的积分面积（初值用，不作定量）。"""
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    fw = estimate_fwhm(x, y, idx)
    mask = np.abs(x - x[idx]) <= 2.0 * fw
    if mask.sum() < 2:
        return float(max(y[idx], 0.0))
    return float(np.trapezoid(np.maximum(y[mask], 0.0), x[mask]))
