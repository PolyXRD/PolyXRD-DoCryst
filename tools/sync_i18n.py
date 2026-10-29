"""校验三语 key 与 zh_CN 完全一致（家族 i18n 铁律：缺译直接报错）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docryst.i18n.translations import en_US, ja_JP, zh_CN


def main() -> int:
    base = set(zh_CN.TRANSLATIONS)
    fail = False
    for name, mod in (("en_US", en_US), ("ja_JP", ja_JP)):
        keys = set(mod.TRANSLATIONS)
        missing = base - keys
        extra = keys - base
        if missing:
            print(f"[{name}] 缺 {len(missing)} 键:", sorted(missing)[:10])
            fail = True
        if extra:
            print(f"[{name}] 多 {len(extra)} 键:", sorted(extra)[:10])
            fail = True
    print("OK" if not fail else "FAIL")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
