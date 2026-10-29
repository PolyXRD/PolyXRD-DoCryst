# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：注册版（Setup 安装包，onedir）。

与内部评估版（PolyXRD-DoCryst.spec）的差异：
- onedir（安装目录 + 支持文件），启动更快；
- 不加 runtime_hook，版次保持 registered —— 启动注册检查、
  帮助菜单「输入注册码」、状态栏注册单位；
- 不排除 docryst.gui.registration。
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
        "docryst.core.dtypes",
        "docryst.core.background",
        "docryst.core.profile",
        "docryst.core.peakfind",
        "docryst.core.fitting",
        "docryst.core.crystallinity",
        "docryst.core.project",
        "docryst.core.report",
        "docryst.core.plot",
        "docryst.core.vendor.model",
        "docryst.core.vendor.raw_formats",
        "docryst.core.vendor.text_formats",
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
        "docryst.gui.registration",
    ],
    hookspath=[],
    hooksconfig={},
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PolyXRD-DoCryst",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["resources/app-icon.ico"],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PolyXRD-DoCryst",
)
