"""峰表：逐峰查看与编辑（峰位/FWHM/η/面积/类型/锁定）。

编辑语义（与拟合参数一一对应）：
- 改峰位 / FWHM / η / 面积 → 立即写回会话并触发**预览重绘**（不自动拟合，
  由用户点「拟合」或打开「编辑后自动拟合」）；
- 改「类型」→ 手动改判（``kind_locked=True``，自动判据不再覆盖）；
- 三个锁定列 → ``fix_pos/fix_fwhm/fix_area``，锁定参数不参与最小二乘
  ——这是「手动拟合」的核心控制手段。

表格行与画布标记双向联动：选中行 ⇔ 画布高亮。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from docryst.core.dtypes import KIND_AMORPHOUS, KIND_CRYSTAL
from docryst.i18n import tr

_COL_SEQ = 0
_COL_POS = 1
_COL_FWHM = 2
_COL_ETA = 3
_COL_AREA = 4
_COL_PCT = 5
_COL_KIND = 6
_COL_FIX_POS = 7
_COL_FIX_FWHM = 8
_COL_FIX_AREA = 9
NCOL = 10

_AMORPH_ALPHA = QColor(252, 211, 77, 70)     # 非晶行底色（琥珀 12% 透明度）


class PeakTable(QTableWidget):
    """峰编辑表。所有写操作以信号上抛，主窗口负责改状态与回填。"""

    #: (行, 字段, 新值)；field ∈ pos/fwhm/eta/area/kind/fix_pos/fix_fwhm/fix_area
    peak_edited = Signal(int, str, object)
    #: 手动删除请求
    peak_delete_requested = Signal(int)
    selection_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, NCOL, parent)
        self._updating = False
        self.setHorizontalHeaderLabels(["#"] + [""] * (NCOL - 1))
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.verticalHeader().setVisible(False)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Stretch)
        for c in (_COL_SEQ, _COL_ETA, _COL_PCT, _COL_KIND,
                  _COL_FIX_POS, _COL_FIX_FWHM, _COL_FIX_AREA):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(_COL_SEQ, QHeaderView.ResizeToContents)
        self.itemChanged.connect(self._on_item_changed)
        self.itemSelectionChanged.connect(self._on_selection)
        self.retranslate()

    # ------------------------------------------------------------------ #
    # 回填
    # ------------------------------------------------------------------ #
    def load_peaks(self, peaks, total_area: float = 0.0,
                   selected: int | None = None) -> None:
        """用峰列表整体重建表格（不触发 peak_edited）。"""
        self._updating = True
        self.setRowCount(len(peaks))
        for i, p in enumerate(peaks):
            pct = (p.area / total_area * 100.0) if total_area > 0 else 0.0
            self._set_row(i, p, pct)
        self._updating = False
        if selected is not None and 0 <= selected < len(peaks):
            self.selectRow(selected)
        self._recolor()

    def _set_row(self, i: int, p, pct: float) -> None:
        items = [
            (str(i + 1), _COL_SEQ, None),
            (f"{p.pos:.3f}", _COL_POS, dict(decimals=3, singlestep=0.01)),
            (f"{p.fwhm:.3f}", _COL_FWHM, dict(decimals=3, singlestep=0.05)),
            (f"{p.eta:.2f}", _COL_ETA, dict(decimals=2, singlestep=0.05)),
            (f"{p.area:.0f}", _COL_AREA, dict(decimals=0, singlestep=100)),
            (f"{pct:.2f}", _COL_PCT, None),
        ]
        for text, col, spin in items:
            it = QTableWidgetItem(text)
            if spin is not None:
                it.setData(Qt.EditRole, float(text.replace(",", "")))
            if col in (_COL_SEQ, _COL_PCT):
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.setItem(i, col, it)

        # 类型下拉
        combo = QComboBox(self)
        combo.addItem(tr("peak.kind_crystal"), KIND_CRYSTAL)
        combo.addItem(tr("peak.kind_amorphous"), KIND_AMORPHOUS)
        combo.setCurrentIndex(1 if p.is_amorphous else 0)
        combo.currentIndexChanged.connect(
            lambda _i, row=i, w=combo: self._on_kind(row, w))
        self.setCellWidget(i, _COL_KIND, combo)

        # 三个锁定列
        for col, attr in ((_COL_FIX_POS, "fix_pos"), (_COL_FIX_FWHM, "fix_fwhm"),
                          (_COL_FIX_AREA, "fix_area")):
            cb = QTableWidgetItem()
            cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            cb.setCheckState(Qt.Checked if getattr(p, attr) else Qt.Unchecked)
            cb.setToolTip({attr: tr("peak.fix.tip." + attr.split("_")[1])}[attr])
            self.setItem(i, col, cb)

    def _recolor(self) -> None:
        # setBackground 会触发 itemChanged，必须挂在 _updating 防护下，
        # 否则与 main_window._sync_table 形成无限递归
        self._updating = True
        try:
            for i in range(self.rowCount()):
                combo = self.cellWidget(i, _COL_KIND)
                is_a = bool(combo and combo.currentData() == KIND_AMORPHOUS)
                for col in range(NCOL):
                    it = self.item(i, col)
                    if it is not None:
                        it.setBackground(_AMORPH_ALPHA if is_a
                                         else QColor(0, 0, 0, 0))
        finally:
            self._updating = False

    # ------------------------------------------------------------------ #
    # 编辑事件
    # ------------------------------------------------------------------ #
    def _on_item_changed(self, it: QTableWidgetItem) -> None:
        if self._updating:
            return
        row, col = it.row(), it.column()
        if col in (_COL_POS, _COL_FWHM, _COL_ETA, _COL_AREA):
            field = {_COL_POS: "pos", _COL_FWHM: "fwhm", _COL_ETA: "eta",
                     _COL_AREA: "area"}[col]
            try:
                val = float(it.text())
            except ValueError:
                return
            self.peak_edited.emit(row, field, val)
        elif col in (_COL_FIX_POS, _COL_FIX_FWHM, _COL_FIX_AREA):
            field = {_COL_FIX_POS: "fix_pos", _COL_FIX_FWHM: "fix_fwhm",
                     _COL_FIX_AREA: "fix_area"}[col]
            self.peak_edited.emit(row, field, it.checkState() == Qt.Checked)

    def _on_kind(self, row: int, combo: QComboBox) -> None:
        if self._updating:
            return
        self.peak_edited.emit(row, "kind", combo.currentData())
        self._recolor()

    def _on_selection(self) -> None:
        row = self.currentRow()
        if row >= 0:
            self.selection_changed.emit(row)

    def keyPressEvent(self, event) -> None:  # noqa: N802（Qt 覆写）
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            row = self.currentRow()
            if 0 <= row < self.rowCount():
                self.peak_delete_requested.emit(row)
                return
        super().keyPressEvent(event)

    def selected_row(self) -> int | None:
        row = self.currentRow()
        return row if 0 <= row < self.rowCount() else None

    def retranslate(self) -> None:
        self.setHorizontalHeaderLabels([
            "#", tr("peak.pos"), tr("peak.fwhm"), tr("peak.eta"),
            tr("peak.area"), tr("peak.area_pct"), tr("peak.kind"),
            tr("peak.fix_pos"), tr("peak.fix_fwhm"), tr("peak.fix_area"),
        ])
