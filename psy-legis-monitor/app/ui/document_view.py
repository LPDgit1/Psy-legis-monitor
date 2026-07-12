"""Presentation helpers for the Streamlit document triage view."""

from __future__ import annotations

import re
from datetime import date, datetime
from html import unescape
from typing import Any

from app.connectors.parsing import infer_italian_region
from app.core.text_cleaning import fold_for_search, normalize_text


PROPOSAL_TYPES = {"disegno_di_legge", "proposta_di_legge"}
NORMATIVE_TYPES = {
    "legge",
    "decreto_legge",
    "decreto_legislativo",
    "regolamento",
    "dgr",
    "bur",
}
INFORMATIONAL_TYPE = "altro"
DIRECT_RELEVANCE_CATEGORIES = {
    "professione_diretta",
    "servizi_psicologici",
    "salute_mentale_servizi",
}
CONTEXTUAL_RELEVANCE_CATEGORIES = {
    "sanita_welfare",
    "scuola_minori_famiglia",
    "clinica_sociale",
    "anziani_lavoro_organizzazioni",
    "tecnologia_ai_privacy",
}
NOISE_PATTERNS = [
    "liquidazione coatta amministrativa",
    "commissario liquidatore",
    "sostituzione del commissario liquidatore",
    "autorizzazione all immissione in commercio del medicinale",
    "importazione parallela del medicinale",
    "rilascio di exequatur",
    "scioglimento del consiglio comunale",
    "disciplinare di produzione",
    "mercato vitivinicolo",
]

ACT_TYPE_LABELS = {
    "disegno_di_legge": "Disegno di legge",
    "proposta_di_legge": "Proposta di legge",
    "legge": "Legge",
    "decreto_legge": "Decreto-legge",
    "decreto_legislativo": "Decreto legislativo",
    "regolamento": "Regolamento",
    "dgr": "DGR / delibera regionale",
    "bur": "Bollettino ufficiale",
    "altro": "News / aggiornamento",
}

STATUS_LABELS = {
    "presentato": "Presentato",
    "assegnato": "Assegnato",
    "in_commissione": "In commissione",
    "approvato": "Approvato",
    "pubblicato": "Pubblicato",
    "decaduto": "Decaduto",
    "sconosciuto": "Da verificare",
}

LEVEL_LABELS = {
    "nazionale": "Nazionale",
    "regionale": "Regionale",
    "europeo": "Europeo",
    "locale": "Locale",
}


def is_mock_row(row: dict[str, Any]) -> bool:
    source = str(row.get("source", "")).lower()
    source_type = str(row.get("source_type", "")).lower()
    return source_type == "mock" or "mock" in source


def document_bucket(row: dict[str, Any]) -> str:
    """Return a coarse UX category for filtering and display."""

    if is_mock_row(row):
        return "mock"
    act_type = row.get("act_type")
    source = str(row.get("source", "")).lower()
    if act_type in PROPOSAL_TYPES:
        return "proposta_legge"
    if act_type in NORMATIVE_TYPES:
        return "atto_normativo"
    if any(
        marker in source
        for marker in [
            "normattiva",
            "parlamento italiano",
            "gazzetta ufficiale",
            "trova norme",
            "ministero della salute - norme",
        ]
    ):
        return "atto_normativo"
    if any(marker in source for marker in ["camera dei deputati", "senato della repubblica"]):
        return "proposta_legge"
    if "eur-lex" in source:
        return "atto_normativo"
    return "informazione"


def is_primary_document(row: dict[str, Any]) -> bool:
    return document_bucket(row) in {"proposta_legge", "atto_normativo"}


def is_relevant_primary_document(row: dict[str, Any]) -> bool:
    """Return whether a primary act has enough thematic signal for the default view."""

    if not is_primary_document(row):
        return False
    found_terms = row.get("found_terms") or {}
    found_categories = set(found_terms)
    if DIRECT_RELEVANCE_CATEGORIES & found_categories:
        return True

    if _matches_noise_pattern(row):
        return False

    score = float(row.get("score") or 0)
    contextual_categories = CONTEXTUAL_RELEVANCE_CATEGORIES & found_categories
    if score >= 15:
        return True
    if score >= 4 and len(contextual_categories) >= 2:
        return True
    return False


def is_potential_primary_document(row: dict[str, Any]) -> bool:
    if not is_primary_document(row) or is_relevant_primary_document(row):
        return False
    if _matches_noise_pattern(row):
        return False
    return float(row.get("score") or 0) >= 1


def _matches_noise_pattern(row: dict[str, Any]) -> bool:
    searchable_text = fold_for_search(
        " ".join(
            str(row.get(key) or "")
            for key in ["title", "summary", "text", "source"]
        )
    )
    return any(pattern in searchable_text for pattern in NOISE_PATTERNS)


def bucket_label(row: dict[str, Any]) -> str:
    labels = {
        "proposta_legge": "Proposta / iter parlamentare",
        "atto_normativo": "Atto normativo",
        "informazione": "News / aggiornamento",
        "mock": "Mock",
    }
    return labels.get(document_bucket(row), "Da classificare")


def document_type_label(row: dict[str, Any]) -> str:
    act_type = row.get("act_type")
    bucket = document_bucket(row)
    level = row.get("level")
    if bucket == "proposta_legge":
        return act_type_label(str(act_type))
    if bucket == "informazione":
        return "News / aggiornamento"
    if act_type == "legge" and level == "regionale":
        return "Legge regionale"
    if act_type == "regolamento" and level == "regionale":
        return "Regolamento regionale"
    if act_type in {"decreto_legge", "decreto_legislativo"} and level == "regionale":
        return "Decreto regionale"
    if act_type == "altro" and bucket == "atto_normativo":
        return "Atto normativo"
    return act_type_label(str(act_type) if act_type else None)


def act_type_label(act_type: str | None) -> str:
    return ACT_TYPE_LABELS.get(act_type or "", act_type or "Da classificare")


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(status or "", status or "Da verificare")


def level_label(level: str | None) -> str:
    return LEVEL_LABELS.get(level or "", level or "")


MOJIBAKE_REPLACEMENTS = {
    "\u00c2\u00b0": "°",
    "\u00c2\u00aa": "a",
    "\u00c2\u00ab": "«",
    "\u00c2\u00bb": "»",
    "\u00c3\u0080": "À",
    "\u00c3\u0088": "È",
    "\u00c3\u0089": "É",
    "\u00c3\u008c": "Ì",
    "\u00c3\u0092": "Ò",
    "\u00c3\u0099": "Ù",
    "\u00c3\u02c6": "È",
    "\u00c3\u0152": "Ì",
    "\u00c3\u00a0": "à",
    "\u00c3\u00a8": "è",
    "\u00c3\u00a9": "é",
    "\u00c3\u00ac": "ì",
    "\u00c3\u00b2": "ò",
    "\u00c3\u00b9": "ù",
    "\u00c32": "ò",
    "\u00c9\u0099": "ə",
    "3\ufffd Serie": "3a Serie",
    "3\u00c2\u00aa Serie": "3a Serie",
    "Vald\ufffdtain": "Valdotain",
}


def clean_display_text(value: object | None) -> str:
    if value is None:
        return ""
    text = _replace_mojibake(str(value))
    text = normalize_text(text)
    text = _replace_mojibake(text)
    text = re.sub(r"</?[^>]+>", "", text)
    return normalize_display_punctuation(text)


def clean_html_cell_text(value: object | None) -> str:
    text = clean_display_text(value)
    for _ in range(6):
        decoded = unescape(text)
        if decoded == text:
            break
        text = clean_display_text(decoded)
    return text


def _replace_mojibake(text: str) -> str:
    for source, replacement in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    text = re.sub(r"\u00c2(?=$|\s)", "", text)
    text = re.sub(r"\u00c3\s+\u0308", "è", text)
    text = re.sub(r"(?<=[A-Za-zÀ-ÿ])\u00c3(?=$|[\s,.;:)\]»])", "à", text)
    return text


def normalize_display_punctuation(text: str) -> str:
    text = text.translate(str.maketrans({"‘": "’", "`": "’", "´": "’"}))
    text = re.sub(r"(?<=\w)'(?=\w)", "’", text)
    text = re.sub(r"([Aa])'(?=$|[^\w])", lambda match: "À" if match.group(1).isupper() else "à", text)
    text = re.sub(r"([Ee])'(?=$|[^\w])", lambda match: "È" if match.group(1).isupper() else "è", text)
    text = re.sub(r"([Ii])'(?=$|[^\w])", lambda match: "Ì" if match.group(1).isupper() else "ì", text)
    text = re.sub(r"([Oo])'(?=$|[^\w])", lambda match: "Ò" if match.group(1).isupper() else "ò", text)
    text = re.sub(r"([Uu])'(?=$|[^\w])", lambda match: "Ù" if match.group(1).isupper() else "ù", text)
    return _curly_double_quotes(text)


def _curly_double_quotes(text: str) -> str:
    result: list[str] = []
    opening = True
    for char in text:
        if char == '"':
            result.append("“" if opening else "”")
            opening = not opening
        else:
            result.append(char)
    return "".join(result)


def display_region(row: dict[str, Any]) -> str:
    region = clean_display_text(row.get("region"))
    if region:
        return region
    if row.get("level") == "regionale":
        inferred = infer_italian_region(
            row.get("title"),
            row.get("summary"),
            row.get("text"),
            row.get("source"),
        )
        return inferred or ""
    return ""


def sort_date_value(value: date | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.min
