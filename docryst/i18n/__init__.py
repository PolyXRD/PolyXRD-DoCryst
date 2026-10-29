"""i18n：三语文案查询与语言切换（re-export 管理器 API）。"""

from __future__ import annotations

from docryst.i18n.i18n_manager import (
    CONFIG_PATH,
    DEFAULT_LANGUAGE,
    LANGUAGE_NAMES,
    available_languages,
    current_language,
    load_language,
    save_language,
    set_language,
    tr,
)

__all__ = [
    "CONFIG_PATH", "DEFAULT_LANGUAGE", "LANGUAGE_NAMES",
    "available_languages", "current_language", "load_language",
    "save_language", "set_language", "tr",
]
