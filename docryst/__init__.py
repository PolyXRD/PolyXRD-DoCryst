"""PolyXRD DoCryst —— XRD 结晶度分峰定量分析工具（PolyXRD 家族成员）。

包结构::

    docryst/core   纯算法（无 Qt 依赖）：背景、峰形、拟合、判据、面积比、报告
    docryst/gui    PySide6 界面：交互式分峰画布、峰表、面板、结果卡
    docryst/i18n   三语（简体中文 / English / 日本語）文案

家族约定（与 PolyXRD / RutAna / CifCalc 一致）：core 不依赖 GUI，
GUI 与 core 之间只经 ``docryst.gui.services`` 交互，便于单元测试与批量。
"""

from __future__ import annotations

from docryst.version import APP_NAME, __version__

__all__ = ["APP_NAME", "__version__"]
