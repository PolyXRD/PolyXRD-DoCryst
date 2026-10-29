"""结果卡：大字号结晶度 + 关键指标行（家族 ResultCard 风格扩展）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from docryst.i18n import tr

#: 指标行 key 顺序（显示顺序即此序）
RESULT_ROWS = (
    "result.area_crystal", "result.area_amorphous", "result.n_peaks",
    "result.threshold", "result.degree_total", "result.coverage",
    "result.rwp", "result.r2",
)

#: 指标颜色语义
_GOOD = "#047857"
_WARN = "#B45309"
_BAD = "#B91C1C"
_MUTED = "#64748B"


class ResultCard(QGroupBox):
    """结晶度结果卡：顶部大数字，下方 2 列指标网格。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        self.lbl_head = QLabel(self)
        self.lbl_head.setAlignment(Qt.AlignCenter)
        self.lbl_head.setStyleSheet("font-size:30px; font-weight:700; color:#0284C7;")
        root.addWidget(self.lbl_head)

        self.lbl_sub = QLabel(self)
        self.lbl_sub.setAlignment(Qt.AlignCenter)
        self.lbl_sub.setStyleSheet("font-size:12px; color:#64748B;")
        root.addWidget(self.lbl_sub)

        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#E2E8F0;")
        root.addWidget(line)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(2)
        self._labels: dict[str, QLabel] = {}
        self._key_labels: dict[str, QLabel] = {}
        for i, key in enumerate(RESULT_ROWS):
            k = QLabel(self)
            k.setStyleSheet("font-size:12px; color:#64748B;")
            v = QLabel(self)
            v.setStyleSheet("font-size:12px; font-weight:600; color:#0F172A;")
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(k, i // 2, (i % 2) * 2)
            grid.addWidget(v, i // 2, (i % 2) * 2 + 1)
            self._labels[key] = v
            self._key_labels[key] = k
        root.addLayout(grid)

        self.lbl_warn = QLabel(self)
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setStyleSheet("font-size:11px; color:#B45309;")
        root.addWidget(self.lbl_warn)
        root.addStretch(1)
        self.clear()
        self.retranslate()

    # ------------------------------------------------------------------ #
    def set_result(self, result) -> None:
        """回填 :class:`CrystResult`。"""
        sigma = f" ± {result.sigma:.2f}" if result.sigma > 0 else ""
        self.lbl_head.setText(f"{result.degree:.2f}<span style='font-size:14px;"
                              f" color:#64748B;'>{sigma} %</span>")
        self.lbl_sub.setText(tr("result.card_subtitle",
                                nc=result.n_crystal, na=result.n_amorphous))
        self.set_value("result.area_crystal", f"{result.area_crystal:.0f}")
        self.set_value("result.area_amorphous", f"{result.area_amorphous:.0f}")
        self.set_value("result.n_peaks",
                       tr("result.n_peaks_fmt", nc=result.n_crystal,
                          na=result.n_amorphous))
        self.set_value("result.threshold", f"> {result.fwhm_threshold:.1f}°")
        self.set_value("result.degree_total", f"{result.degree_total:.2f} %",
                       _color_of_total(result))
        self.set_value("result.coverage", f"{result.coverage * 100:.1f} %",
                       _GOOD if result.coverage >= 0.95 else _WARN)
        self.set_value("result.rwp", f"{result.rwp * 100:.2f} %",
                       _GOOD if result.rwp <= 0.10 else (_WARN if result.rwp <= 0.15 else _BAD))
        self.set_value("result.r2", f"{result.r2:.5f}",
                       _GOOD if result.r2 >= 0.99 else _WARN)
        if result.warnings:
            self.lbl_warn.setText("\n".join(f"⚠ {tr(k)}" for k in result.warnings))
        else:
            self.lbl_warn.setText(tr("result.no_warning"))
        self.lbl_warn.setToolTip(f"{result.halo_edge_ratio * 100:.1f} %"
                                 if result.halo_edge_ratio else "")

    def set_value(self, key: str, text: str, color: str = "#0F172A") -> None:
        lbl = self._labels[key]
        lbl.setText(text)
        lbl.setStyleSheet(f"font-size:12px; font-weight:600; color:{color};")

    def clear(self) -> None:
        self.lbl_head.setText("--")
        self.lbl_sub.setText(tr("result.card_subtitle_empty"))
        for key in RESULT_ROWS:
            self.set_value(key, "—", _MUTED)
        self.lbl_warn.setText("")

    def retranslate(self) -> None:
        """语言切换后刷新指标行名（值由下次 set_result / clear 回填）。"""
        self.setTitle(tr("result.group"))
        for key in RESULT_ROWS:
            self._key_labels[key].setText(tr(key))


def _color_of_total(result) -> str:
    """总面积法与主口径的偏差提示色（>2 pp 视为口径差异显著）。"""
    try:
        diff = abs(result.degree - result.degree_total)
    except (TypeError, ValueError):
        return "#0F172A"
    if diff <= 2.0:
        return _GOOD
    if diff <= 5.0:
        return _WARN
    return _BAD
