"""交互式分峰画布（matplotlib QtAgg）。

交互约定（与 Jade 的分峰操作同思路，键位按现代习惯）：
- **加峰模式**：左键点击谱图任意位置 → 在该 2θ 处新增一个峰
  （初值由局部峰高/半宽估计，信号 ``peak_add_requested``）；
- **选择模式**（默认）：
  - 左键按住某峰的标记线拖动 → 实时预览（``drag_preview``），
    松开落位（``peak_moved``）；
  - 右键点击某峰标记 → 删除该峰（``peak_delete_requested``）；
  - 左键点击某峰标记 → 选中（``peak_selected``，峰表同步高亮）；
- 谱图本体支持滚轮缩放与左键框选放大（matplotlib 导航栏），加峰/拖峰
  模式下导航栏自动让位（模式互斥）。

画布不持有分析状态：``update_model`` 只负责画，所有交互都以信号上抛，
由主窗口改状态后回填。
"""

from __future__ import annotations

import numpy as np
import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget

matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

from docryst.i18n import tr

# 家族色板
OBS = "#0284C7"
CALC = "#0F172A"
BG_LINE = "#94A3B8"
DIFF = "#DC2626"
GRID = "#CBD5E1"
FILL_CRYSTAL = "#7DD3FC"
FILL_AMORPH = "#FCD34D"
EDGE_CRYSTAL = "#0369A1"
EDGE_AMORPH = "#B45309"
SEL_COLOR = "#E11D48"

MODE_SELECT = "select"
MODE_ADD = "add"

#: 判定点选命中的像素半径
PICK_RADIUS_PX = 12.0


class PatternCanvas(FigureCanvasQTAgg):
    """谱图 + 分解结果 + 峰标记的交互画布。"""

    peak_add_requested = Signal(float)
    peak_delete_requested = Signal(int)
    peak_selected = Signal(int)
    peak_moved = Signal(int, float)
    drag_preview = Signal(int, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        self.figure = Figure(figsize=(5.6, 4.4), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self.mode = MODE_SELECT
        self._x: np.ndarray | None = None
        self._y: np.ndarray | None = None
        self._peaks: list = []          # 当前峰参数（用于标记/命中测试）
        self._has_model = False
        self._drag_idx: int | None = None
        self._mpl_cids: list[int] = []
        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_release_event", self._on_release)
        self._show_empty()

    # ------------------------------------------------------------------ #
    # 数据回填
    # ------------------------------------------------------------------ #
    def set_pattern(self, x: np.ndarray, y: np.ndarray) -> None:
        """只显示谱图（导入后、未分析时）。"""
        self._x, self._y = np.asarray(x), np.asarray(y)
        self._peaks = []
        self._has_model = False
        self._redraw()

    def update_model(self, x, y_obs, y_bg, comps, kinds, peaks, *,
                     selected: int | None = None) -> None:
        """显示完整分解（分析/预览后由主窗口回填）。"""
        self._x = np.asarray(x)
        self._y = np.asarray(y_obs)
        self._bg = np.asarray(y_bg)
        self._comps = list(comps)
        self._kinds = list(kinds)
        self._peaks = list(peaks)
        self._has_model = True
        self._selected = selected
        self._redraw()

    def set_peaks(self, peaks: list) -> None:
        """只更新峰标记（不重画曲线——峰表编辑时避免整幅重绘）。"""
        self._peaks = list(peaks)
        if self._has_model:
            self._redraw()

    def set_selected(self, idx: int | None) -> None:
        """设置选中峰（-1/None 取消），并重画标记高亮。"""
        self._selected = None if idx is None or idx < 0 else idx
        if self._has_model:
            self._redraw()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.setCursor(Qt.CursorShape.CrossCursor if mode == MODE_ADD
                       else Qt.CursorShape.ArrowCursor)

    def clear(self) -> None:
        self._x = self._y = None
        self._peaks = []
        self._has_model = False
        self._show_empty()
        self.draw_idle()

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #
    def _show_empty(self) -> None:
        self.figure.clf()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor("white")
        ax.text(0.5, 0.5, tr("canvas.empty"), ha="center", va="center",
                fontsize=11, color="#64748B", transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        self.figure.tight_layout()

    def _redraw(self) -> None:
        if self._x is None or self._y is None:
            self._show_empty()
            self.draw_idle()
            return
        self.figure.clf()
        if self._has_model:
            self.ax_main, self.ax_diff = self.figure.subplots(
                2, 1, height_ratios=[2.4, 1], sharex=True)
        else:
            self.ax_main = self.figure.add_subplot(111)
            self.ax_diff = None

        x, y = self._x, self._y
        if self._has_model:
            bg = self._bg
            self.ax_main.plot(x, y, linestyle="none", marker="x", color=OBS,
                              markersize=2.2, markeredgewidth=0.5,
                              label=tr("canvas.legend.obs"))
            self.ax_main.plot(x, self._calc_cache(), color=CALC, lw=1.0,
                              label=tr("canvas.legend.calc"))
            self.ax_main.plot(x, bg, color=BG_LINE, lw=0.9, ls="--",
                              label=tr("canvas.legend.bg"))
            for comp, kind in zip(self._comps, self._kinds):
                c_fill = FILL_AMORPH if kind == "amorphous" else FILL_CRYSTAL
                c_edge = EDGE_AMORPH if kind == "amorphous" else EDGE_CRYSTAL
                comp = np.maximum(np.asarray(comp), 0.0)
                self.ax_main.fill_between(x, bg, bg + comp, color=c_fill,
                                          alpha=0.40, linewidth=0)
                self.ax_main.plot(x, bg + comp, color=c_edge, lw=0.55)
            self.ax_main.legend([
                self.ax_main.lines[0], self.ax_main.lines[1],
                self.ax_main.lines[2]],
                [tr("canvas.legend.obs"), tr("canvas.legend.calc"),
                 tr("canvas.legend.bg")],
                loc="upper right", fontsize=8, frameon=False)
            diff = y - self._calc_cache()
            self.ax_diff.plot(x, diff, color=DIFF, lw=0.7)
            self.ax_diff.axhline(0.0, color=GRID, lw=0.6)
            self.ax_diff.set_ylabel(tr("canvas.y_diff"))
            self.ax_diff.set_xlabel(tr("canvas.x_label"))
            self.ax_diff.grid(True, color=GRID, lw=0.4, alpha=0.5)
        else:
            self.ax_main.plot(x, y, color=CALC, lw=0.9)

        self.ax_main.set_ylabel(tr("canvas.y_label"))
        self.ax_main.grid(True, color=GRID, lw=0.4, alpha=0.5)
        self.ax_main.set_xlim(x[0], x[-1])

        # 峰标记：竖线 + 序号（选中高亮）
        for i, p in enumerate(self._peaks):
            top = float(self._marker_top(p))
            color = SEL_COLOR if getattr(self, "_selected", None) == i else (
                EDGE_AMORPH if p.is_amorphous else EDGE_CRYSTAL)
            self.ax_main.vlines(p.pos, 0.0, top, color=color, lw=1.4,
                                alpha=0.9, zorder=5)
            self.ax_main.annotate(
                str(i + 1), (p.pos, top), xytext=(0, 4),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=7.5, color=color, zorder=6)
        self.figure.tight_layout()
        self.draw_idle()

    def _calc_cache(self) -> np.ndarray:
        calc = np.asarray(self._bg, dtype=float).copy()
        for comp in self._comps:
            calc = calc + np.asarray(comp, dtype=float)
        return calc

    def _marker_top(self, p) -> float:
        """峰标记竖线顶端（背景 + 峰高）。"""
        base = float(np.interp(p.pos, self._x, self._calc_cache())) \
            if self._has_model else 0.0
        return base + p.height

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #
    def _xy_data(self, event) -> tuple[float, float] | None:
        if event.inaxes != self.ax_main or self._x is None:
            return None
        return float(event.xdata), float(event.ydata)

    def _hit_peak(self, xdata: float) -> int | None:
        """返回与 xdata 水平距离最近且在命中半径内的峰下标。"""
        if not self._peaks:
            return None
        # 像素半径换算为数据坐标
        inv = self.ax_main.transData.inverted()
        (x0, _), (x1, _) = inv.transform((0, 0)), inv.transform(
            (PICK_RADIUS_PX, 0))
        tol = abs(x1 - x0)
        best, best_d = None, tol
        for i, p in enumerate(self._peaks):
            d = abs(p.pos - xdata)
            if d <= best_d:
                best, best_d = i, d
        return best

    def _on_press(self, event) -> None:
        if event.inaxes != self.ax_main or self._x is None:
            return
        if event.button == 1 and self.mode == MODE_ADD:
            if event.xdata is not None:
                self.peak_add_requested.emit(float(event.xdata))
            return
        if event.button == 3:
            if event.xdata is not None:
                idx = self._hit_peak(float(event.xdata))
                if idx is not None:
                    self.peak_delete_requested.emit(idx)
            return
        if event.button == 1 and self.mode == MODE_SELECT and event.xdata is not None:
            idx = self._hit_peak(float(event.xdata))
            if idx is not None:
                self._drag_idx = idx
                self.peak_selected.emit(idx)

    def _on_motion(self, event) -> None:
        if (self._drag_idx is None or event.inaxes != self.ax_main
                or event.xdata is None):
            return
        if self.mode != MODE_SELECT:
            self._drag_idx = None
            return
        self.drag_preview.emit(self._drag_idx, float(event.xdata))

    def _on_release(self, event) -> None:
        if self._drag_idx is not None and event.xdata is not None:
            self.peak_moved.emit(self._drag_idx, float(event.xdata))
        self._drag_idx = None
