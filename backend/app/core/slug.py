"""Slug generation helper with Cyrillic transliteration.

Used to build human/URL-friendly slugs for campaign documents from their
(usually Russian) titles. No external dependency — a small transliteration map
covers ru/en; everything else is stripped to hyphens.
"""

import re

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(text: str, *, fallback: str = "document") -> str:
    """Transliterate, lowercase, and hyphenate ``text`` into a URL-safe slug.

    Returns ``fallback`` if the result would be empty (e.g. title was only
    punctuation). Trimmed to 200 chars to stay well under the column limit.
    """
    text = (text or "").lower().strip()
    out = "".join(_TRANSLIT.get(ch, ch) for ch in text)
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    out = re.sub(r"-{2,}", "-", out)
    return out[:200] or fallback
