from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOCALES_DIR = Path(__file__).parent.parent / "locales"


@lru_cache(maxsize=8)
def _load(lang: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        path = LOCALES_DIR / "en.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def t(lang: str, key: str, **kwargs: object) -> str:
    """Translate *key* in *lang*, falling back to English."""
    strings = _load(lang)
    text = strings.get(key) or _load("en").get(key) or key
    return text.format(**kwargs) if kwargs else text
