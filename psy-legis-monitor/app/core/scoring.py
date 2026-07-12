"""YAML-driven keyword scoring."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.config.settings import load_yaml, settings
from app.core.schemas import LegislativeDocument, ScoreResult
from app.core.text_cleaning import fold_for_search


DEFAULT_THRESHOLDS = {"alta": 15.0, "media": 8.0, "bassa": 1.0}


def _iter_terms(terms_config: Any) -> list[tuple[str, float]]:
    if isinstance(terms_config, dict):
        return [(str(term), float(weight)) for term, weight in terms_config.items()]
    if isinstance(terms_config, list):
        parsed: list[tuple[str, float]] = []
        for item in terms_config:
            if isinstance(item, str):
                parsed.append((item, 1.0))
            elif isinstance(item, dict):
                for term, weight in item.items():
                    parsed.append((str(term), float(weight)))
        return parsed
    return []


def _count_term(text: str, term: str) -> int:
    folded_term = fold_for_search(term)
    if not folded_term:
        return 0
    pattern = re.compile(rf"(?<!\w){re.escape(folded_term)}(?!\w)")
    return len(pattern.findall(text))


def _class_from_score(total_score: float, thresholds: dict[str, float]) -> str:
    if total_score >= thresholds.get("alta", DEFAULT_THRESHOLDS["alta"]):
        return "alta"
    if total_score >= thresholds.get("media", DEFAULT_THRESHOLDS["media"]):
        return "media"
    if total_score >= thresholds.get("bassa", DEFAULT_THRESHOLDS["bassa"]):
        return "bassa"
    return "irrilevante"


def score_document(
    document: LegislativeDocument,
    keywords_path: str | Path | None = None,
) -> ScoreResult:
    """Score a document using only configurable YAML keyword groups."""

    config = load_yaml(keywords_path or settings.keywords_path)
    categories = config.get("categories", {})
    thresholds = {**DEFAULT_THRESHOLDS, **config.get("thresholds", {})}
    searchable_text = fold_for_search(
        " ".join(
            part
            for part in [document.title, document.summary or "", document.text]
            if part
        )
    )

    total_score = 0.0
    category_scores: dict[str, float] = {}
    found_terms: dict[str, list[str]] = {}

    for category, category_config in categories.items():
        category_weight = float(category_config.get("weight", 1.0))
        category_score = 0.0
        matches: list[str] = []
        for term, term_weight in _iter_terms(category_config.get("terms", [])):
            occurrences = _count_term(searchable_text, term)
            if occurrences:
                category_score += occurrences * term_weight * category_weight
                matches.append(term)
        if category_score:
            category_scores[category] = round(category_score, 2)
            found_terms[category] = sorted(set(matches), key=str.lower)
            total_score += category_score

    return ScoreResult(
        total_score=round(total_score, 2),
        category_scores=category_scores,
        found_terms=found_terms,
        relevance_class=_class_from_score(total_score, thresholds),
    )

