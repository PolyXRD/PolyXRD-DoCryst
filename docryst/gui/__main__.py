"""GUI 入口：``python -m docryst.gui``。

启动流程：QSplashScreen（resources/splash-screen.png，1.2 s 后自动关闭）
→ 主窗口。资源缺失时优雅降级（不阻塞启动）。打包态（PyInstaller onefile）
下 bootloader 解压阶段由 spec 的 ``Splash`` 显示同图启动画面，主窗口 show 后
经 :func:`_close_boot_splash` 关闭该下层启动图（家族统一实现，同 RutAna）。
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from docryst.version import APP_NAME
from docryst.gui.resources import resource_path

#: 启动图展示时长（毫秒）
SPLASH_MS = 1200


def _close_boot_splash() -> None:
    """关闭 PyInstaller bootloader 启动图（仅打包态且 spec 配置了 Splash 时）。

    以 ``_PYI_SPLASH_IPC`` 环境变量守卫：未配置 Splash 的构建（如 Setup 版）
    里 pyi_splash 模块虽可能存在但 import 即报 KeyError 并向 stderr 打印
    噪音，先查环境变量可彻底避免。
    """
    import os

    if not os.environ.get("_PYI_SPLASH_IPC"):
        return
    try:
        import pyi_splash

        pyi_splash.close()
    except Exception:
        pass  # 开发态或启动图已失效 —— 静默跳过


def main() -> int:
    """创建应用、启动图与主窗口，进入事件循环。"""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")

    icon_path = resource_path("app-icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    splash = None
    splash_path = resource_path("splash-screen.png")
    if splash_path.exists():
        pixmap = QPixmap(str(splash_path))
        if not pixmap.isNull():
            splash = QSplashScreen(pixmap)
            splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            splash.show()
            app.processEvents()

    # 延迟导入主窗口，让启动图先出现
    from docryst.gui.main_window import MainWindow

    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.startup_registration)
    _close_boot_splash()
    if splash is not None:
        QTimer.singleShot(SPLASH_MS, splash.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
