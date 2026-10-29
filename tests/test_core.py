"""合成真值验证：核心算法的面积闭合、参数恢复与判据行为。

真值口径：合成谱由面积参数化的 pV 生成，解析真值
``C_true = ΣA_cryst / (ΣA_cryst + ΣA_amor)``（全窗解析面积，与报告主口径一致）。
无噪恢复目标 < 0.5 pp，含噪（σ≈12 counts）< 2 pp。
"""

from __future__ import annotations

import numpy as np
import pytest

from docryst.core import fitting as fitmod
from docryst.core.background import (
    BG_NONE,
    anchor_curve,
    evaluate as bg_eval,
    linear_end_points,
    snip_background,
)
from docryst.core.crystallinity import auto_analyze, summarize
from docryst.core.dtypes import (
    BackgroundConfig,
    Pattern,
    PeakSpec,
)
from docryst.core.peakfind import FindOptions, classify, find_peaks
from docryst.core.profile import (
    estimate_fwhm,
    pseudo_voigt,
    pv_area_from_height,
    pv_fwhm_from_area_height,
    pv_height,
)
from docryst.core import project, report

TRUE_PEAKS = [
    PeakSpec(21.0, 0.18, 12000.0, 0.6),
    PeakSpec(26.5, 0.22, 30000.0, 0.6),
    PeakSpec(36.2, 0.25, 8000.0, 0.6),
    PeakSpec(24.0, 9.0, 60000.0, 0.8),
]
TRUE_C = 100.0 * sum(p.area for p in TRUE_PEAKS[:3]) / sum(p.area for p in TRUE_PEAKS)


def synth(x=None, noise=0.0, baseline=0.0, seed=7, peaks=None) -> Pattern:
    rng = np.random.default_rng(seed)
    if x is None:
        x = np.arange(5.0, 80.0, 0.02)
    y = np.full_like(x, baseline, dtype=float)
    for p in (peaks or TRUE_PEAKS):
        y += pseudo_voigt(x, p.pos, p.fwhm, p.area, p.eta)
    if noise:
        y += rng.normal(0.0, noise, size=x.size)
    return Pattern(x, np.maximum(y, 0.0))


# --------------------------------------------------------------------------- #
# 峰形：面积闭合
# --------------------------------------------------------------------------- #
def test_pv_area_closed_analytic():
    """数值积分（宽窗口）应与解析面积一致到 0.5% 以内（纯高斯）。"""
    x = np.linspace(10.0, 40.0, 30000)
    y = pseudo_voigt(x, 25.0, 0.3, 5000.0, 0.0)
    assert abs(np.trapezoid(y, x) - 5000.0) / 5000.0 < 0.005


def test_pv_lorentz_tail_extends():
    """纯洛伦兹峰的解析面积应在宽窗口内同样闭合（峰尾很宽，窗口取大）。"""
    x = np.linspace(-500.0, 550.0, 2_000_001)
    y = pseudo_voigt(x, 25.0, 0.3, 5000.0, 1.0)
    assert abs(np.trapezoid(y, x) - 5000.0) / 5000.0 < 0.02


def test_height_area_roundtrip():
    h = 100.0
    for eta in (0.0, 0.5, 1.0):
        a = pv_area_from_height(0.25, h, eta)
        assert pv_height(0.25, a, eta) == pytest.approx(h, rel=1e-9)
        f = pv_fwhm_from_area_height(a, h, eta)
        assert f == pytest.approx(0.25, rel=1e-9)


def test_estimate_fwhm_on_clean_peak():
    x = np.arange(20.0, 30.0, 0.005)
    y = pseudo_voigt(x, 25.0, 0.4, 1000.0, 0.5)
    idx = int(np.argmax(y))
    assert estimate_fwhm(x, y, idx) == pytest.approx(0.4, rel=0.05)


# --------------------------------------------------------------------------- #
# 背景
# --------------------------------------------------------------------------- #
def test_linear_end_points_uses_median():
    x = np.arange(0.0, 10.0, 0.01)
    y = np.where((x < 0.06) | (x > 9.94), 100.0, 5.0)
    y_lo, y_hi = linear_end_points(x, y, n_end=5)
    assert y_lo == pytest.approx(100.0)
    assert y_hi == pytest.approx(100.0)


def test_anchor_curve_piecewise():
    x = np.array([0.0, 5.0, 10.0])
    curve = anchor_curve(x, [(0.0, 10.0), (10.0, 30.0)])
    assert curve[0] == pytest.approx(10.0)
    assert curve[1] == pytest.approx(20.0)
    assert curve[2] == pytest.approx(30.0)


def test_snip_removes_sharp_keeps_broad():
    """SNIP 应削掉尖峰、大体保留宽包（这正是它不能用于结晶度定量的原因）。"""
    x = np.arange(10.0, 60.0, 0.02)
    y = (pseudo_voigt(x, 30.0, 0.2, 20000.0, 0.6)
         + pseudo_voigt(x, 30.0, 12.0, 30000.0, 0.5))
    bg = snip_background(x, y, n_iter=60)
    # 尖峰处背景应远低于净峰高
    i = int(np.argmin(np.abs(x - 30.0)))
    assert bg[i] < y[i] * 0.2


def test_background_eval_models_run():
    pat = synth()
    for model in ("none", "linear_ends", "anchors", "snip"):
        cfg = BackgroundConfig(model, anchors=[(5.0, 0.0), (80.0, 0.0)])
        curve = bg_eval(pat.two_theta, pat.intensity, cfg)
        assert curve.shape == pat.intensity.shape


# --------------------------------------------------------------------------- #
# 寻峰
# --------------------------------------------------------------------------- #
def test_find_peaks_detects_sharp_and_halo():
    pat = synth(noise=8.0)
    bg = np.zeros_like(pat.two_theta)
    peaks = find_peaks(pat.two_theta, np.maximum(pat.intensity - bg, 0.0),
                       FindOptions(prominence_frac=0.01))
    poss = [p.pos for p in peaks]
    assert any(abs(p - 26.5) < 0.3 for p in poss)
    assert any(abs(p - 21.0) < 0.3 for p in poss)


def test_classify_threshold_and_manual_lock():
    peaks = [PeakSpec(20.0, 0.2, 100.0), PeakSpec(30.0, 5.0, 200.0)]
    out = classify(peaks, 3.0)
    assert out[0].kind == "crystal" and out[1].kind == "amorphous"
    # 手动锁定的峰不被自动判据覆盖
    peaks[0].kind_locked = True
    peaks[0].kind = "amorphous"
    out = classify(peaks, 3.0)
    assert out[0].kind == "amorphous"


# --------------------------------------------------------------------------- #
# 拟合与结晶度恢复
# --------------------------------------------------------------------------- #
def test_noiseless_recovery_exact():
    pat = synth()
    res = auto_analyze(pat, BackgroundConfig(BG_NONE), fwhm_threshold=3.0)
    assert res.degree == pytest.approx(TRUE_C, abs=0.5)
    assert res.n_amorphous == 1 and res.n_crystal == 3
    assert res.fit.success
    # 参数级恢复
    fitted = {round(p.pos, 1): p for p in res.fit.peaks}
    assert fitted[24.0].fwhm == pytest.approx(9.0, abs=0.3)
    assert fitted[24.0].area == pytest.approx(60000.0, rel=0.02)
    assert fitted[26.5].area == pytest.approx(30000.0, rel=0.02)


def test_noisy_recovery_within_2pp():
    for seed in (3, 11, 23):
        pat = synth(noise=12.0, seed=seed)
        res = auto_analyze(pat, BackgroundConfig("poly"), fwhm_threshold=3.0)
        assert res.degree == pytest.approx(TRUE_C, abs=2.0), f"seed={seed}"


def test_decreasing_background_poly():
    """递减指数背景：多项式背景应把偏差压在 1 pp 内。"""
    rng = np.random.default_rng(3)
    x = np.arange(5.0, 80.0, 0.02)
    bg = 40.0 + 260.0 * np.exp(-(x - 5.0) / 22.0)
    y = bg.copy()
    for p in TRUE_PEAKS:
        y += pseudo_voigt(x, p.pos, p.fwhm, p.area, p.eta)
    y += rng.normal(0.0, 10.0, size=x.size)
    res = auto_analyze(Pattern(x, np.maximum(y, 0.0)),
                       BackgroundConfig("poly", order=3), fwhm_threshold=3.0)
    assert res.degree == pytest.approx(TRUE_C, abs=1.0)


def test_pure_amorphous_and_pure_crystal():
    amor = [PeakSpec(24.0, 9.0, 60000.0, 0.8)]
    r1 = auto_analyze(synth(peaks=amor), BackgroundConfig(BG_NONE),
                      fwhm_threshold=3.0)
    assert r1.degree == pytest.approx(0.0, abs=0.5)
    assert r1.n_crystal == 0

    cryst = [p for p in TRUE_PEAKS[:3]]
    r2 = auto_analyze(synth(peaks=cryst), BackgroundConfig(BG_NONE),
                      fwhm_threshold=3.0)
    assert r2.degree == pytest.approx(100.0, abs=0.5)
    assert r2.n_amorphous == 0
    assert "warn.no_amorphous" in r2.warnings


def test_fix_pos_respected():
    """锁定峰位后拟合不得移动峰位（手动拟合的核心语义）。"""
    pat = synth(noise=6.0)
    peaks = [p.copy(fix_pos=True) for p in TRUE_PEAKS[:2]]
    fit = fitmod.fit(pat.two_theta, pat.intensity, peaks,
                     BackgroundConfig(BG_NONE), fitmod.FitOptions())
    for got, want in zip(fit.peaks, TRUE_PEAKS[:2]):
        assert got.pos == pytest.approx(want.pos, abs=1e-6)


def test_area_parameter_semantics():
    """拟合得到的 area 即积分面积：Σ解析面积 ≈ 观测谱扣背景积分（无噪）。"""
    pat = synth()
    res = auto_analyze(pat, BackgroundConfig(BG_NONE), fwhm_threshold=3.0)
    assert res.area_all == pytest.approx(sum(p.area for p in TRUE_PEAKS), rel=0.01)


def test_sigma_positive_and_reasonable():
    pat = synth(noise=12.0)
    res = auto_analyze(pat, BackgroundConfig("poly"), fwhm_threshold=3.0)
    assert 0.0 < res.sigma < 2.0


def test_no_peak_found_returns_empty_result():
    x = np.arange(5.0, 80.0, 0.02)
    pat = Pattern(x, np.full_like(x, 50.0))   # 平坦无峰
    res = auto_analyze(pat, BackgroundConfig("poly"), fwhm_threshold=3.0)
    assert not res.fit.success
    assert "warn.no_peaks" in res.warnings


# --------------------------------------------------------------------------- #
# 工程存档 / 报告
# --------------------------------------------------------------------------- #
def test_project_roundtrip(tmp_path):
    pat = synth()
    res = auto_analyze(pat, BackgroundConfig("poly"), fwhm_threshold=3.0)
    path = project.save_project(
        tmp_path / "p.dcy.json", pattern_path="s.xy", sample="s",
        lo=None, hi=None, bg_cfg=BackgroundConfig("poly"),
        peaks=res.fit.peaks, fwhm_threshold=3.0,
        result={"degree": res.degree})
    data = project.load_project(path)
    peaks2 = project.peaks_from_project(data)
    bg2 = project.background_from_project(data)
    assert len(peaks2) == len(res.fit.peaks)
    assert bg2.model == "poly"
    # 用存档峰表复算：C 必须复现
    res2 = auto_analyze(pat, bg2, fwhm_threshold=data["fwhm_threshold"],
                        peaks=peaks2)
    assert res2.degree == pytest.approx(res.degree, abs=0.3)


def test_report_and_csv(tmp_path):
    pat = synth()
    res = auto_analyze(pat, BackgroundConfig("poly"), fwhm_threshold=3.0)
    png = tmp_path / "f.png"
    from docryst.core.plot import render_png
    render_png(str(png), pat.two_theta, res.fit.y_obs, res.fit.y_calc,
               res.fit.y_bg, res.fit.components,
               [p.kind for p in res.fit.peaks], 3.0)
    html = report.build_html_report(sample="T", file_name="t.xy", result=res,
                                    png_path=str(png))
    assert "T" in html and "data:image/png;base64" in html
    csv = report.build_csv(res, sample="T", file_name="t.xy")
    assert csv.count("\n") >= len(res.peaks) + 5
