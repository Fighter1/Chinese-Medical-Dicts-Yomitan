"""Generate Hanyu Pinyin lookup readings for headwords.

The source dictionaries carry no pronunciation data, so readings are produced
with pypinyin (phrase-aware, tone marks, ``ü``). Han characters become
space-separated syllables; runs of other characters (digits, Latin, Greek,
punctuation) are kept verbatim so a reading still lines up with its headword.
"""
from __future__ import annotations

import re
import string
import unicodedata

from pypinyin import Style, load_single_dict, pinyin

HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003134f]")
# Rare characters restored from private-use placeholders (see content.PUA_MAP).
load_single_dict({0x2C317: "hé", 0x2BAC7: "è"})

# Quotation marks and brackets around a headword part carry no pronunciation.
STRIPPED = frozenset("“”‘’\"'〔〕[]【】《》〈〉「」『』()（）·•")


def normalize_pinyin(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\x00", ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Co" and ch not in STRIPPED)
    return re.sub(r"\s+", " ", value).strip()


def is_clean_reading(value: str) -> bool:
    """Character hygiene only: Latin letters present, no Han, control or private-use characters."""
    if not value:
        return True
    if value != normalize_pinyin(value):
        return False
    decomposed = unicodedata.normalize("NFD", value)
    return (
        any(ch in string.ascii_letters for ch in decomposed)
        and not HAN.search(value)
        and all(unicodedata.category(ch) not in {"Co", "Cc", "Cf", "Zl", "Zp"} for ch in decomposed)
    )


def reading_for(expression: str) -> str:
    """Return the pinyin reading, or ``""`` when the headword has no Han characters."""
    if not HAN.search(expression):
        return ""
    tokens = [item[0] for item in pinyin(expression, style=Style.TONE, v_to_u=True, heteronym=False)]
    parts: list[str] = []
    for token in tokens:
        token = normalize_pinyin(token)
        if token:
            parts.append(token)
    return normalize_pinyin(" ".join(parts))
