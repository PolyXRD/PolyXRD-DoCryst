"""离屏绘图：分析谱图渲染（PNG 导出 / HTML 报告内嵌 / GUI 画布共用一套样式）。

样式继承家族 v1.2.0 拟合谱口径并做结晶度扩展：
- 实测谱：蓝色 ``×`` 散点（无连线）；
- 拟合谱：黑色实线；背景：灰色虚线；
- 结晶分量：天蓝填充；非晶分量：琥珀填充（视觉上立刻区分 Ac / Aa）；
- 误差线（差值）：红色实线，下方面板。
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")           # 离屏渲染；GUI 画布单独用 QtAgg 后端
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

# CJK 字体（画布/报告中的中文标签）
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

# 家族色板
OBS = "#0284C7"       # 实测散点
CALC = "#0F172A"      # 拟合实线
BG_LINE = "#94A3B8"   # 背景虚线
DIFF = "#DC2626"      # 差值
GRID = "#CBD5E1"
FILL_CRYSTAL = "#7DD3FC"   # 结晶分量填充（天蓝）
FILL_AMORPH = "#FCD34D"    # 非晶分量填充（琥珀）
EDGE_CRYSTAL = "#0369A1"
EDGE_AMORPH = "#B45309"

AMORPH_ALPHA = 0.45


def draw_analysis(fig: Figure, x: np.ndarray, y_obs: np.ndarray,
                  y_calc: np.ndarray, y_bg: np.ndarray,
                  components: list[np.ndarray], kinds: list[str],
                  threshold: float, *,
                  labels: dict[str, str] | None = None) -> None:
    """在给定 Figure 上绘制完整分析图（上下双面板，共用 x 轴）。

    ``labels`` 为图例文案（已本地化）：键 ``obs`` / ``calc`` / ``bg`` /
    ``diff`` / ``crystal`` / ``amorph``；缺省用英文短词。
    """
    lab = {"obs": "Observed", "calc": "Calculated", "bg": "Background",
           "diff": "Difference", "crystal": "Crystalline",
           "amorph": "Amorphous", **(labels or {})}
    fig.clf()
    ax_main, ax_diff = fig.subplots(2, 1, height_ratios=[2.4, 1], sharex=True)

    tt = np.asarray(x, dtype=float)
    ax_main.plot(tt, np.asarray(y_obs, dtype=float), linestyle="none", marker="x",
                 color=OBS, markersize=2.4, markeredgewidth=0.5, label=lab["obs"])
    ax_main.plot(tt, np.asarray(y_calc, dtype=float), color=CALC, lw=1.0,
                 label=lab["calc"])
    ax_main.plot(tt, np.asarray(y_bg, dtype=float), color=BG_LINE, lw=0.9,
                 ls="--", label=lab["bg"])

    for comp, kind in zip(components, kinds):
        color = FILL_AMORPH if kind == "amorphous" else FILL_CRYSTAL
        edge = EDGE_AMORPH if kind == "amorphous" else EDGE_CRYSTAL
        ax_main.fill_between(tt, np.asarray(y_bg, dtype=float),
                             y_bg + np.maximum(comp, 0.0),
                             color=color, alpha=AMORPH_ALPHA, linewidth=0)
        ax_main.plot(tt, y_bg + np.maximum(comp, 0.0), color=edge, lw=0.6)

    # 图例：手工构造（分量填充只各出现一次）
    from matplotlib.patches import Patch
    handles = [
        ax_main.lines[0], ax_main.lines[1], ax_main.lines[2],
        Patch(facecolor=FILL_CRYSTAL, alpha=AMORPH_ALPHA, label=lab["crystal"]),
        Patch(facecolor=FILL_AMORPH, alpha=AMORPH_ALPHA, label=lab["amorph"]),
    ]
    ax_main.legend(handles,
                   [lab["obs"], lab["calc"], lab["bg"], lab["crystal"], lab["amorph"]],
                   loc="upper right", fontsize=8, frameon=False, ncol=2)

    ax_main.set_ylabel("Intensity (counts)")
    ax_main.grid(True, color=GRID, lw=0.4, alpha=0.5)
    ax_main.set_xlim(tt[0], tt[-1])

    diff = np.asarray(y_obs, dtype=float) - np.asarray(y_calc, dtype=float)
    ax_diff.plot(tt, diff, color=DIFF, lw=0.7, label=lab["diff"])
    ax_diff.axhline(0.0, color=GRID, lw=0.6)
    ax_diff.set_xlabel("2Theta (deg)")
    ax_diff.set_ylabel("Diff")
    ax_diff.grid(True, color=GRID, lw=0.4, alpha=0.5)
    ax_diff.tick_params(labelbottom=True)
    ax_diff.set_xlim(tt[0], tt[-1])
    fig.tight_layout()


def render_png(path: str, x, y_obs, y_calc, y_bg, components, kinds,
               threshold: float, *, dpi: int = 150,
               labels: dict[str, str] | None = None) -> str:
    """渲染分析图并保存 PNG，返回路径。"""
    fig = Figure(figsize=(7.2, 5.0), dpi=dpi)
    draw_analysis(fig, x, y_obs, y_calc, y_bg, components, kinds, threshold,
                  labels=labels)
    fig.savefig(path, dpi=dpi, facecolor="white")
    return path
