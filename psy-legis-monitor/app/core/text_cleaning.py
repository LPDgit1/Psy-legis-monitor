"""Utilities for deterministic text normalization."""

from __future__ import annotations

import re
import unicodedata
from html import unescape


WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str | None) -> str:
    """Normalize text for comparison, hashing and keyword matching."""

    if not text:
        return ""
    normalized = text
    for _ in range(3):
        decoded = unescape(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = normalized.replace("\u00a0", " ")
    normalized = WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()


def fold_for_search(text: str | None) -> str:
    """Return lowercase, accent-insensitive text for rule matching."""

    cleaned = normalize_text(text).lower()
    decomposed = unicodedata.normalize("NFD", cleaned)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
