"""后台线程与忙窗：拟合/批量不冻结界面。

- :class:`Worker`：QThread 包装任意 callable，完成/异常经信号回主线程；
  循环型任务（批量）经 ``cancel()`` 协作式终止。
- :class:`BusyDialog`：无边框模态忙窗，任务说明 + 已用时 + 可选取消。
"""

from __future__ import annotations

import time
import traceback

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QWidget

from docryst.i18n import tr

COLOR_MUTED = "#64748B"

#: 忙窗标题（窗口级，不随语言切换重建）
APP_TITLE = "PolyXRD DoCryst"


class Worker(QThread):
    """通用后台任务：携带任意 callable，完成/异常经信号回主线程。"""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, parent=None, **kw) -> None:
        super().__init__(parent)
        self._fn = fn
        self._args = args
        self._kw = kw
        self.cancelled = False

    def cancel(self) -> None:
        """协作式取消：只有循环型任务（批量）会检查该标志。"""
        self.cancelled = True

    def run(self) -> None:
        try:
            self.done.emit(self._fn(*self._args, **self._kw))
        except Exception:  # noqa: BLE001 —— 异常文本回主线程统一弹窗
            self.failed.emit(traceback.format_exc())


class BusyDialog(QDialog):
    """模态忙窗：任务说明 + 已用时 + 取消（可选）。

    用法：``dlg = BusyDialog(self, message)`` → 启动 Worker →
    Worker 完成信号里 ``dlg.accept()``。取消经 ``dlg.result() == QDialog.Rejected``
    判断（对单次拟合即时生效：轻量任务忽略取消）。
    """

    def __init__(self, parent: QWidget | None = None,
                 message: str = "", cancelable: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle(APP_TITLE)
        self.setModal(True)
        self.setFixedWidth(340)
        root = QVBoxLayout(self)
        self.lbl_msg = QLabel(message or tr("busy.working"), self)
        self.lbl_msg.setStyleSheet(
            "font-size:14px; font-weight:600; color:#0F172A;")
        self.lbl_msg.setWordWrap(True)
        root.addWidget(self.lbl_msg)
        self.lbl_elapsed = QLabel("0.0 s", self)
        self.lbl_elapsed.setStyleSheet(f"font-size:12px; color:{COLOR_MUTED};")
        root.addWidget(self.lbl_elapsed)
        self.btn_cancel: QPushButton | None = None
        if cancelable:
            self.btn_cancel = QPushButton(tr("busy.cancel"), self)
            self.btn_cancel.clicked.connect(self.reject)
            root.addWidget(self.btn_cancel)
        self._t0 = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self.lbl_elapsed.setText(f"{time.perf_counter() - self._t0:.1f} s")

    def set_message(self, text: str) -> None:
        self.lbl_msg.setText(text)
