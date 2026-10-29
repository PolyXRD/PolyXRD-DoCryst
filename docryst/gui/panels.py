"""右侧参数面板：区间 / 背景 / 判据 / 拟合选项 / 动作按钮。

面板只采集参数与发信号，不直接调用 core —— 经主窗口 → services。
所有文案经 i18n，``retranslate()`` 支持运行时热切换。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from docryst.core.dtypes import (
    BG_LINEAR_ENDS,
    BG_LINEAR_LSQ,
    BG_NONE,
    BG_POLY,
    BG_SNIP,
    DEFAULT_FWHM_AMORPH,
)
from docryst.gui.resultcard import ResultCard
from docryst.i18n import tr

#: 背景模型 → (标识, 进阶标记)
BG_MODELS = (
    (BG_POLY, False),
    (BG_LINEAR_ENDS, False),
    (BG_LINEAR_LSQ, True),
    (BG_NONE, False),
    (BG_SNIP, True),
)


class ControlPanel(QWidget):
    """参数与动作面板（不含峰表与结果卡，见 main_window 布局）。"""

    auto_requested = Signal()
    fit_requested = Signal()
    undo_requested = Signal()
    range_changed = Signal()
    params_changed = Signal()
    add_mode_requested = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # ---- 拟合区间 ----
        self.grp_range = QGroupBox(self)
        g1 = QGridLayout(self.grp_range)
        self.lbl_lo = QLabel(self.grp_range)
        self.lbl_hi = QLabel(self.grp_range)
        self.sp_lo = QDoubleSpinBox(self.grp_range)
        self.sp_hi = QDoubleSpinBox(self.grp_range)
        for sp in (self.sp_lo, self.sp_hi):
            sp.setRange(0.0, 160.0)
            sp.setDecimals(2)
            sp.setSingleStep(0.5)
        self.sp_lo.valueChanged.connect(lambda _v=0.0: self._emit_range())
        self.sp_hi.valueChanged.connect(lambda _v=0.0: self._emit_range())
        self.btn_full_range = QPushButton(self.grp_range)
        self.btn_full_range.clicked.connect(self._on_full_range)
        g1.addWidget(self.lbl_lo, 0, 0)
        g1.addWidget(self.sp_lo, 0, 1)
        g1.addWidget(self.lbl_hi, 0, 2)
        g1.addWidget(self.sp_hi, 0, 3)
        g1.addWidget(self.btn_full_range, 1, 0, 1, 4)
        root.addWidget(self.grp_range)

        # ---- 背景 ----
        self.grp_bg = QGroupBox(self)
        g2 = QGridLayout(self.grp_bg)
        self.lbl_bg_model = QLabel(self.grp_bg)
        self.cmb_bg = QComboBox(self.grp_bg)
        for _key, _adv in BG_MODELS:
            self.cmb_bg.addItem("")
        self.lbl_bg_order = QLabel(self.grp_bg)
        self.sp_bg_order = QSpinBox(self.grp_bg)
        self.sp_bg_order.setRange(2, 5)
        self.lbl_bg_note = QLabel(self.grp_bg)
        self.lbl_bg_note.setWordWrap(True)
        self.lbl_bg_note.setStyleSheet("font-size:11px; color:#64748B;")
        g2.addWidget(self.lbl_bg_model, 0, 0)
        g2.addWidget(self.cmb_bg, 0, 1)
        g2.addWidget(self.lbl_bg_order, 1, 0)
        g2.addWidget(self.sp_bg_order, 1, 1)
        g2.addWidget(self.lbl_bg_note, 2, 0, 1, 2)
        self.cmb_bg.currentIndexChanged.connect(self._on_bg_changed)
        self.sp_bg_order.valueChanged.connect(lambda _v=0: self.params_changed.emit())
        root.addWidget(self.grp_bg)

        # ---- 判据与拟合 ----
        self.grp_fit = QGroupBox(self)
        g3 = QGridLayout(self.grp_fit)
        self.lbl_threshold = QLabel(self.grp_fit)
        self.sp_threshold = QDoubleSpinBox(self.grp_fit)
        self.sp_threshold.setRange(0.5, 15.0)
        self.sp_threshold.setDecimals(1)
        self.sp_threshold.setSingleStep(0.5)
        self.sp_threshold.setValue(DEFAULT_FWHM_AMORPH)
        self.sp_threshold.valueChanged.connect(lambda _v=0.0: self.params_changed.emit())
        self.chk_autoadd = QCheckBox(self.grp_fit)
        self.chk_autoadd.setChecked(True)
        self.chk_tie_eta = QCheckBox(self.grp_fit)
        self.chk_robust = QCheckBox(self.grp_fit)
        for w in (self.chk_autoadd, self.chk_tie_eta, self.chk_robust):
            # toggled(bool) 与无参信号不兼容，经 lambda 丢弃参数
            w.toggled.connect(lambda _on=False: self.params_changed.emit())
        g3.addWidget(self.lbl_threshold, 0, 0)
        g3.addWidget(self.sp_threshold, 0, 1)
        g3.addWidget(self.chk_autoadd, 1, 0, 1, 2)
        g3.addWidget(self.chk_tie_eta, 2, 0, 1, 2)
        g3.addWidget(self.chk_robust, 3, 0, 1, 2)
        root.addWidget(self.grp_fit)

        # ---- 动作 ----
        hb = QHBoxLayout()
        self.btn_auto = QPushButton(self)
        self.btn_auto.setStyleSheet(
            "font-weight:600; color:white; background:#0284C7;"
            "border-radius:6px; padding:6px 10px;")
        self.btn_auto.clicked.connect(self.auto_requested.emit)
        self.btn_fit = QPushButton(self)
        self.btn_fit.clicked.connect(self.fit_requested.emit)
        self.btn_undo = QPushButton(self)
        self.btn_undo.clicked.connect(self.undo_requested.emit)
        hb.addWidget(self.btn_auto)
        hb.addWidget(self.btn_fit)
        hb.addWidget(self.btn_undo)
        root.addLayout(hb)

        # ---- 加峰模式 ----
        self.chk_add_mode = QCheckBox(self)
        self.chk_add_mode.toggled.connect(self.add_mode_requested.emit)
        self.lbl_add_hint = QLabel(self)
        self.lbl_add_hint.setWordWrap(True)
        self.lbl_add_hint.setStyleSheet("font-size:11px; color:#64748B;")
        root.addWidget(self.chk_add_mode)
        root.addWidget(self.lbl_add_hint)

        root.addStretch(1)
        self.retranslate()

    # ------------------------------------------------------------------ #
    # 参数读取
    # ------------------------------------------------------------------ #
    def bg_config(self):
        from docryst.core.dtypes import BackgroundConfig

        model = self.cmb_bg.currentData() or BG_POLY
        return BackgroundConfig(model=model, order=int(self.sp_bg_order.value()))

    def set_bg_config(self, model: str, order: int = 3) -> None:
        for i, (key, _adv) in enumerate(BG_MODELS):
            if key == model:
                self.cmb_bg.setCurrentIndex(i)
                break
        self.sp_bg_order.setValue(order)

    def threshold(self) -> float:
        return float(self.sp_threshold.value())

    def range_values(self) -> tuple[float | None, float | None]:
        return float(self.sp_lo.value()), float(self.sp_hi.value())

    def set_range(self, lo: float, hi: float) -> None:
        """写入区间（含数据全范围上下界）。"""
        for sp in (self.sp_lo, self.sp_hi):
            sp.blockSignals(True)
        self.sp_lo.setRange(0.0, max(160.0, hi))
        self.sp_hi.setRange(0.0, max(160.0, hi))
        self.sp_lo.setValue(lo)
        self.sp_hi.setValue(hi)
        for sp in (self.sp_lo, self.sp_hi):
            sp.blockSignals(False)

    def fit_options(self):
        from docryst.core import fitting as fitmod

        # fit_background 恒为 True：是否真正释放背景参数由背景模型自身决定
        # （poly/linear_lsq 有自由参数，linear_ends/anchors/snip/none 为固定）
        return fitmod.FitOptions(
            fit_background=True,
            tie_eta=self.chk_tie_eta.isChecked(),
            robust=self.chk_robust.isChecked(),
        )

    def auto_add_peaks(self) -> bool:
        return self.chk_autoadd.isChecked()

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _emit_range(self) -> None:
        if self.sp_lo.value() < self.sp_hi.value():
            self.range_changed.emit()

    def _on_full_range(self) -> None:
        lo, hi = self._data_span
        self.set_range(lo, hi)
        self.range_changed.emit()

    def _on_bg_changed(self, _idx: int) -> None:
        self.params_changed.emit()
        self.retranslate()

    def set_data_span(self, lo: float, hi: float) -> None:
        self._data_span = (lo, hi)

    _data_span = (0.0, 90.0)

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self.grp_range.setTitle(tr("panel.range"))
        self.lbl_lo.setText(tr("panel.range.lo"))
        self.lbl_hi.setText(tr("panel.range.hi"))
        self.btn_full_range.setText(tr("panel.range.full"))
        self.grp_bg.setTitle(tr("panel.bg"))
        self.lbl_bg_model.setText(tr("panel.bg.model"))
        self.lbl_bg_order.setText(tr("panel.bg.order"))
        self.lbl_bg_note.setText(tr("panel.bg.note"))
        for i, (key, adv) in enumerate(BG_MODELS):
            self.cmb_bg.setItemText(i, tr("bg." + key) + ("  *" if adv else ""))
        self.grp_fit.setTitle(tr("panel.fit"))
        self.lbl_threshold.setText(tr("panel.threshold"))
        self.sp_threshold.setToolTip(tr("panel.threshold.tip"))
        self.chk_autoadd.setText(tr("panel.autoadd"))
        self.chk_tie_eta.setText(tr("panel.tie_eta"))
        self.chk_robust.setText(tr("panel.robust"))
        self.btn_auto.setText(tr("panel.auto"))
        self.btn_fit.setText(tr("panel.fit"))
        self.btn_undo.setText(tr("panel.undo"))
        self.chk_add_mode.setText(tr("panel.add_mode"))
        self.lbl_add_hint.setText(tr("panel.add_hint"))


class ResultDock(QWidget):
    """右侧下半区：峰表 + 结果卡的容器（垂直分割）。"""

    def __init__(self, table, card, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QVBoxLayout

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        root.addWidget(table, 3)
        root.addWidget(card, 2)
