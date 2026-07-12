"""Shared parsing helpers for institutional source connectors."""

from __future__ import annotations

import re
from datetime import date

from app.core.text_cleaning import fold_for_search, normalize_text


ITALIAN_MONTHS = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}


def parse_connector_date(value: object | None) -> date | None:
    """Parse dates commonly exposed by Italian institutional pages and APIs."""

    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = normalize_text(str(value))
    if not text:
        return None

    for pattern in (r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b"):
        match = re.search(pattern, text)
        if match:
            year, month, day = (int(part) for part in match.groups())
            return _safe_date(year, month, day)

    match = re.search(r"\b(\d{4})(\d{2})(\d{2})\b", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return _safe_date(year, month, day)

    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if match:
        day, month, year = (int(part) for part in match.groups())
        return _safe_date(year, month, day)

    folded = fold_for_search(text)
    month_names = "|".join(ITALIAN_MONTHS)
    match = re.search(rf"\b(\d{{1,2}})\s+({month_names})\s+(\d{{4}})\b", folded)
    if match:
        day = int(match.group(1))
        month = ITALIAN_MONTHS[match.group(2)]
        year = int(match.group(3))
        return _safe_date(year, month, day)
    return None


def infer_act_type(text: str | None, *, default: str = "altro") -> str:
    folded = fold_for_search(text)
    if "decreto-legge" in folded or "decreto legge" in folded or re.search(r"\bdl\b", folded):
        return "decreto_legge"
    if "decreto legislativo" in folded or "d.lgs" in folded or "dlgs" in folded:
        return "decreto_legislativo"
    if "disegno di legge" in folded or re.search(r"\bddl\b", folded):
        return "disegno_di_legge"
    if "proposta di legge" in folded:
        return "proposta_di_legge"
    if "legge regionale" in folded or folded.startswith("legge ") or " legge " in folded:
        return "legge"
    if "regolamento" in folded:
        return "regolamento"
    if "delibera" in folded or "deliberazione" in folded or re.search(r"\bdgr\b", folded):
        return "dgr"
    if "bollettino ufficiale" in folded or re.search(r"\bbur\b|\bburl\b", folded):
        return "bur"
    return default


def infer_status(text: str | None, *, default: str = "sconosciuto") -> str:
    folded = fold_for_search(text)
    if "decadut" in folded:
        return "decaduto"
    if "approvato" in folded or "approvata" in folded:
        return "approvato"
    if "commissione" in folded:
        return "in_commissione"
    if "assegn" in folded:
        return "assegnato"
    if "pubblicat" in folded or "vigente" in folded or "multivigenza" in folded:
        return "pubblicato"
    if "presentat" in folded or "trasmess" in folded:
        return "presentato"
    return default


def first_non_blank(*values: object | None) -> str | None:
    for value in values:
        text = normalize_text(str(value)) if value is not None else ""
        if text:
            return text
    return None


def compact_identifier(value: str | None) -> str | None:
    if not value:
        return None
    text = normalize_text(value)
    return text or None


REGION_ALIASES = {
    "Abruzzo": ["abruzzo", "abruzzese"],
    "Basilicata": ["basilicata", "lucana", "lucano"],
    "Calabria": ["calabria", "calabrese"],
    "Campania": ["campania", "campana", "campano"],
    "Emilia-Romagna": ["emilia-romagna", "emilia romagna", "emiliano-romagnola"],
    "Friuli Venezia Giulia": ["friuli venezia giulia", "friuli-venezia giulia", "friul"],
    "Lazio": ["lazio", "laziale"],
    "Liguria": ["liguria", "ligure"],
    "Lombardia": ["lombardia", "lombarda", "lombardo"],
    "Marche": ["marche", "marchigiana", "marchigiano"],
    "Molise": ["molise", "molisana", "molisano"],
    "Piemonte": ["piemonte", "piemontese"],
    "Puglia": ["puglia", "pugliese"],
    "Sardegna": ["sardegna", "sarda", "sardo"],
    "Sicilia": ["sicilia", "siciliana", "siciliano", "regione siciliana"],
    "Toscana": ["toscana", "toscana"],
    "Trentino-Alto Adige": ["trentino-alto adige", "trentino alto adige"],
    "Umbria": ["umbria", "umbra", "umbro"],
    "Valle d'Aosta": ["valle d'aosta", "valdostana", "valdostano"],
    "Veneto": ["veneto", "veneta", "veneto"],
    "Provincia autonoma di Bolzano": [
        "provincia autonoma di bolzano",
        "provincia di bolzano",
        "alto adige",
        "sudtirol",
    ],
    "Provincia autonoma di Trento": [
        "provincia autonoma di trento",
        "provincia di trento",
        "trentino",
    ],
}


def infer_italian_region(*values: object | None) -> str | None:
    text = fold_for_search(" ".join(str(value) for value in values if value))
    if not text:
        return None
    for region, aliases in REGION_ALIASES.items():
        for alias in aliases:
            folded_alias = fold_for_search(alias)
            if re.search(rf"(?<!\w){re.escape(folded_alias)}(?!\w)", text):
                return region
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
