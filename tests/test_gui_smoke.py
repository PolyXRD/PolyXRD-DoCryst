"""GUI 冒烟测试（QT_QPA_PLATFORM=offscreen）：不弹窗、不阻塞。

流程：构造窗口 → 写合成谱 → 导入 → 直接调用分析 job（绕开线程/忙窗）→
断言结果卡、峰表、画布状态；再验证加峰/删峰/编辑/撤销/语言切换不崩。
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("POLYXRD_REG_NO_PROMPT", "1")

import numpy as np
import pytest

from docryst.core.dtypes import BackgroundConfig, PeakSpec
from docryst.core.profile import pseudo_voigt


@pytest.fixture(scope="module")
def pattern_file(tmp_path_factory):
    """合成谱文件（3 尖峰 + 1 宽包 + 端点直线背景，真值 C=45.45）。"""
    rng = np.random.default_rng(5)
    x = np.arange(5.0, 80.0, 0.02)
    truth = [PeakSpec(21.0, 0.18, 12000.0, 0.6),
             PeakSpec(26.5, 0.22, 30000.0, 0.6),
             PeakSpec(36.2, 0.25, 8000.0, 0.6),
             PeakSpec(24.0, 9.0, 60000.0, 0.8)]
    y = np.full_like(x, 60.0)
    for p in truth:
        y += pseudo_voigt(x, p.pos, p.fwhm, p.area, p.eta)
    y += rng.normal(0.0, 12.0, size=x.size)
    path = tmp_path_factory.mktemp("data") / "synthetic.xy"
    np.savetxt(path, np.column_stack([x, y]), fmt="%.4f %.2f")
    return str(path), (100.0 * sum(p.area for p in truth[:3])
                       / sum(p.area for p in truth))


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, pattern_file):
    from docryst.gui.main_window import MainWindow

    win = MainWindow()
    path, _true = pattern_file
    win._import_paths([path])
    assert win.file_list.count() == 1
    return win


def _run_job(win, job):
    """直接执行分析 job（offscreen 下绕开忙窗线程）。"""
    sess = win._session()
    result = job(sess)
    win._on_analysis_done(result)


def test_full_flow_auto_analyze(window, pattern_file):
    path, true_c = pattern_file
    _run_job(window, window._job_auto)
    sess = window._session()
    assert sess.result is not None
    assert sess.result.degree == pytest.approx(true_c, abs=2.0)
    assert sess.result.n_amorphous >= 1
    # 结果卡大数字已回填
    assert "±" in window.result_card.lbl_head.text() or \
        window.result_card.lbl_head.text() != "--"
    # 峰表行数 = 拟合峰数
    assert window.peak_table.rowCount() == len(sess.result.fit.peaks)
    # 画布已显示模型
    assert window.canvas._has_model


def test_manual_peak_add_delete_undo(window):
    _run_job(window, window._job_auto)
    sess = window._session()
    n0 = len(sess.result.fit.peaks)
    window._on_canvas_add_peak(50.0)
    assert len(window._active_peaks(sess)) == n0 + 1
    window._delete_peak(n0)
    assert len(window._active_peaks(sess)) == n0
    window._on_undo()
    assert len(window._active_peaks(sess)) == n0 + 1


def test_peak_edit_and_kind_lock(window):
    _run_job(window, window._job_auto)
    sess = window._session()
    peaks = window._active_peaks(sess)
    # 找一个结晶峰，改判为非晶
    idx = next(i for i, p in enumerate(peaks) if not p.is_amorphous)
    window._on_peak_edited(idx, "kind", "amorphous")
    assert peaks[idx].kind == "amorphous"
    assert peaks[idx].kind_locked
    # 改 FWHM（预览重绘不拟合）
    window._on_peak_edited(idx, "fwhm", 1.5)
    assert peaks[idx].fwhm == pytest.approx(1.5)
    # 重新拟合后，手动改判不被 summarize 的自动分类覆盖
    _run_job(window, window._job_fit)
    result = window._session().result
    assert result.peaks[idx].kind == "amorphous"


def test_fit_job_respects_fix_flags(window):
    _run_job(window, window._job_auto)
    sess = window._session()
    peaks = window._active_peaks(sess)
    peaks[0].fix_pos = True
    pos_before = peaks[0].pos
    _run_job(window, window._job_fit)
    peaks2 = window._active_peaks(sess)
    assert peaks2[0].pos == pytest.approx(pos_before, abs=1e-6)


def test_language_switch_and_dialogs(window):
    for lang in ("en_US", "ja_JP", "zh_CN"):
        window._on_language(lang)
        assert "⟪" not in window.windowTitle()
    from docryst.gui.dialogs import AboutDialog, CopyrightDialog, MethodDialog
    for cls in (AboutDialog, CopyrightDialog, MethodDialog):
        dlg = cls(window)
        txt = dlg.browser.toPlainText() if hasattr(dlg, "browser") else dlg.lbl_version.text()
        assert "⟪" not in txt


def test_params_collect_and_preview(window):
    _run_job(window, window._job_auto)
    sess = window._session()
    params = window._collect_params(sess)
    assert params.bg_cfg is not None
    assert params.peaks  # 峰表非空
    x, y, bg, comps, _calc = __import__("docryst.gui.services", fromlist=["x"]).preview_curves(sess.pattern, params)
    assert x.size == y.size == bg.size
    assert len(comps) == len(params.peaks)
