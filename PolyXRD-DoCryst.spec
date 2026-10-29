# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（PolyXRD 家族模板，参照 PolyXRD-RutAna spec）。

单文件（onefile）免安装 exe = 内部评估版：
- 入口 docryst/gui/__main__.py（python -m docryst.gui 等价）；
- datas 携带 resources/（品牌资产）；
- bootloader Splash 启动画面（resources/splash-screen.png），onefile 解压
  阶段即显示，主窗口就绪后由 __main__._close_boot_splash 关闭；
- 版本号从 docryst/version.py 读取，exe 名与 build_exe.bat 的副本逻辑对应；
- runtime_hook 覆写版次为 internal，并彻底排除注册模块。
"""

import re
from pathlib import Path

_ver = re.search(
    r'__version__\s*=\s*"([^"]+)"',
    Path("docryst/version.py").read_text(encoding="utf-8"),
).group(1)

datas = [("resources", "resources")]

a = Analysis(
    ["docryst/gui/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "docryst",
        "docryst.version",
        "docryst.edition",
        "docryst.i18n",
        "docryst.i18n.i18n_manager",
        "docryst.i18n.translations.zh_CN",
        "docryst.i18n.translations.en_US",
        "docryst.i18n.translations.ja_JP",
        # core 算法模块（与 docryst/core 下真实模块逐一核对）
        "docryst.core.dtypes",
        "docryst.core.background",
        "docryst.core.profile",
        "docryst.core.peakfind",
        "docryst.core.fitting",
        "docryst.core.crystallinity",
        "docryst.core.project",
        "docryst.core.report",
        "docryst.core.plot",
        # 读谱器 vendor 副本（源自 PolyXRD-Converter）
        "docryst.core.vendor.model",
        "docryst.core.vendor.raw_formats",
        "docryst.core.vendor.text_formats",
        # gui
        "docryst.gui.resources",
        "docryst.gui.services",
        "docryst.gui.batch",
        "docryst.gui.canvas",
        "docryst.gui.panels",
        "docryst.gui.peaktable",
        "docryst.gui.dialogs",
        "docryst.gui.main_window",
        "docryst.gui.workers",
        "docryst.gui.resultcard",
    ],
    hookspath=[],
    hooksconfig={},
    # 内部评估版：运行时覆写版次 + 排除注册模块（exe 不含注册机制）
    runtime_hooks=["installer/rthook_internal.py"],
    excludes=["docryst.gui.registration"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# bootloader 启动图（onefile 解压期即显示品牌图；splash.binaries 必须作为
# 独立 TOC 参数传入 EXE，否则解压期找不到 Tcl/Tk，启动画面静默失败）
splash = Splash(
    "resources/splash-screen.png",
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    text_size=12,
    min_font_color="white",
    always_on_top=True,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    splash,
    splash.binaries,
    [],
    name=f"PolyXRD-DoCryst-v{_ver}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["resources/app-icon.ico"],
)
