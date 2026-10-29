"""版次标识：registered=注册版（Setup 安装包）| internal=内部评估版（单文件 exe）。

默认 registered（源码运行即注册版行为）；打包时经 PyInstaller runtime_hook
（installer/rthook_internal.py）覆写为 internal，且在 spec 中 excludes 掉
``docryst.gui.registration``，使内部评估版 exe 内不含注册机制。

运行期只读：主窗口按 ``edition.IS_INTERNAL`` 决定是否接入注册机制——
internal 版次状态栏居中显示「内部评估版本」、帮助菜单无「输入注册码」；
registered 版次每次启动检查注册、状态栏右侧显示注册单位。
测试可 monkeypatch 模块属性切换版次。
"""

EDITION = "registered"
IS_INTERNAL = EDITION == "internal"
