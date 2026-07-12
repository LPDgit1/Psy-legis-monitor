"""Stable identity and text hashing helpers."""

from __future__ import annotations

import hashlib

from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import normalize_text


def stable_text_hash(text: str | None) -> str:
    """Hash normalized text so cosmetic whitespace changes do not create noise."""

    cleaned = normalize_text(text)
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def document_identity_key(document: LegislativeDocument) -> str:
    """Build a stable deduplication key with explicit fallbacks."""

    identifier = document.identifier or ""
    url = document.url or ""
    if identifier:
        raw = f"{document.source}|{identifier}"
    elif url:
        raw = f"{document.source}|{url}"
    else:
        raw = f"{document.source}|{document.title}|{document.date_published or ''}"
    return stable_text_hash(raw)
