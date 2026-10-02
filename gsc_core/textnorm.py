"""Query text handling that works for Japanese as well as English.

Search Console keeps "食パン　レシピ" (full-width space), "食パン レシピ" and
"食パン ﾚｼﾋﾟ" (half-width katakana) as separate rows. They are the same search, so for
comparison they are merged under one NFKC-normalised key; the most-seen spelling is displayed.
"""

from __future__ import annotations

import re
import unicodedata

_SPACE = re.compile(r"\s+")
_JA = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")


def normalize_query(text: str) -> str:
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text or "")).strip().lower()


def has_japanese(text: str) -> bool:
    return bool(_JA.search(text or ""))


def detect_language(weighted_texts) -> str:
    """'ja' when at least 30% of impressions are on Japanese-script queries, else 'en'."""
    total = ja = 0.0
    for text, weight in weighted_texts:
        total += weight
        if has_japanese(text):
            ja += weight
    return "ja" if total and ja / total >= 0.3 else "en"


def shorten(text: str, limit: int = 40) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"
