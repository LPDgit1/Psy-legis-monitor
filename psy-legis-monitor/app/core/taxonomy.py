"""Rule-based thematic taxonomy classification."""

from __future__ import annotations

from pathlib import Path

from app.config.settings import load_yaml, settings
from app.core.scoring import _count_term
from app.core.schemas import LegislativeDocument, TaxonomyClassification
from app.core.text_cleaning import fold_for_search


def classify_taxonomy(
    document: LegislativeDocument,
    taxonomy_path: str | Path | None = None,
) -> TaxonomyClassification:
    config = load_yaml(taxonomy_path or settings.taxonomy_path)
    areas = config.get("areas", {})
    searchable_text = fold_for_search(
        " ".join([document.title, document.summary or "", document.text])
    )
    matches: dict[str, list[str]] = {}

    for area_name, area_config in areas.items():
        keywords = area_config.get("keywords", [])
        found = [term for term in keywords if _count_term(searchable_text, term)]
        if found:
            matches[area_name] = sorted(set(found), key=str.lower)

    return TaxonomyClassification(domains=list(matches.keys()), matches=matches)

