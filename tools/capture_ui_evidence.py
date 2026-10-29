"""离屏（QT_QPA_PLATFORM=offscreen）抓取 DoCryst UI 证据图。

用法（PySide6 可用的解释器）::

    python tools/capture_ui_evidence.py [输出目录]

输出目录缺省 ``docs/evidence/``。合成谱带 3 尖峰 + 1 宽非晶包（真值 C≈45.45），
跑一遍自动分析后抓主窗口，另抓关于/方法对话框。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("POLYXRD_REG_NO_PROMPT", "1")

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from docryst.core.dtypes import PeakSpec  # noqa: E402
from docryst.core.profile import pseudo_voigt  # noqa: E402

DEFAULT_OUT = Path("docs") / "evidence"


def _synthetic(path: Path) -> None:
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
    np.savetxt(path, np.column_stack([x, y]), fmt="%.4f %.2f")


def _grab(widget, path: Path) -> Path:
    widget.show()
    app = QApplication.instance()
    for _ in range(30):
        app.processEvents()
        time.sleep(0.01)
    QApplication.processEvents()
    pix = widget.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(path), "PNG")
    return path


def capture(out_dir: Path) -> list[Path]:
    from docryst.gui.dialogs import AboutDialog, MethodDialog
    from docryst.gui.main_window import MainWindow
    from docryst.i18n import set_language

    set_language("zh_CN")
    app = QApplication.instance() or QApplication([])

    data = ROOT / "tests" / "out" / "_evidence_synthetic.xy"
    _synthetic(data)

    win = MainWindow()
    win.resize(1500, 900)
    win._import_paths([str(data)])
    # 直接执行分析 job（offscreen 下绕开忙窗线程）
    result = win._job_auto(win._session())
    win._on_analysis_done(result)
    paths = [_grab(win, out_dir / "01_main_window.png")]

    for name, dlg in (("02_about.png", AboutDialog(win)),
                      ("03_method.png", MethodDialog(win))):
        dlg.resize(dlg.size().expandedTo(win.size() * 0.5))
        paths.append(_grab(dlg, out_dir / name))
        dlg.close()
    win.close()
    return paths


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / DEFAULT_OUT
    for p in capture(out):
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
