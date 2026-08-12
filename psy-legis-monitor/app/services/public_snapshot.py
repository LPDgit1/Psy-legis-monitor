"""Build the public, privacy-safe document snapshot consumed by Sites."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Iterable, Mapping

from app.core.hashing import document_identity_key
from app.core.schemas import LegislativeDocument
from app.core.scoring import score_document
from app.core.taxonomy import classify_taxonomy
from app.ui.document_view import (
    clean_display_text,
    document_type_label,
    is_excluded_noise_document,
    is_potential_primary_document,
    is_relevant_primary_document,
)


PUBLIC_SNAPSHOT_SCHEMA_VERSION = 1

TOPIC_LABELS = {
    "professione_psicologica_e_ordinamento": "Professione psicologica",
    "psicoterapia_e_clinica": "Psicoterapia e clinica",
    "counseling_e_supporto_psicologico": "Supporto psicologico",
    "psicologia_cure_primarie": "Cure primarie",
    "psicologia_scolastica": "Scuola",
    "salute_mentale_territoriale": "Salute mentale",
    "neuropsichiatria_minori_famiglia": "Minori e famiglia",
    "violenza_trauma_emergenza": "Violenza e trauma",
    "dipendenze": "Dipendenze",
    "disabilita_autismo_neurodivergenze": "Disabilita e autismo",
    "anziani_demenze_non_autosufficienza": "Anziani e non autosufficienza",
    "lavoro_organizzazioni_burnout": "Lavoro e burnout",
    "carcere_giustizia": "Giustizia",
    "migrazione_marginalita_inclusione": "Inclusione",
    "formazione_professioni_sanitarie": "Professioni sanitarie",
    "privacy_dati_sanitari_sanita_digitale": "Privacy e sanita digitale",
    "intelligenza_artificiale_tecnologie_psicologiche": "Intelligenza artificiale",
    "welfare_lea_servizi_sociosanitari": "Welfare e servizi",
    "competenze_professionali_criticita": "Competenze professionali",
}

REGIONAL_SOURCE_NAMES = {
    "Abruzzo": "Regione Abruzzo - BURA",
    "Basilicata": "Regione Basilicata - BUR",
    "Calabria": "Regione Calabria - BURC",
    "Campania": "Regione Campania - BURC",
    "Emilia-Romagna": "Regione Emilia-Romagna - BURERT",
    "Friuli Venezia Giulia": "Regione Friuli Venezia Giulia - BUR",
    "Lazio": "Regione Lazio - BUR",
    "Liguria": "Regione Liguria - BURL",
    "Lombardia": "Regione Lombardia - BURL",
    "Marche": "Regione Marche - BUR",
    "Molise": "Regione Molise - BURM",
    "Piemonte": "Regione Piemonte - BURP",
    "Puglia": "Regione Puglia - BURP",
    "Sardegna": "Regione Sardegna - BURAS",
    "Sicilia": "Regione Siciliana - GURS",
    "Toscana": "Regione Toscana - BURT",
    "Trentino-Alto Adige": "Regione Trentino-Alto Adige - BUR",
    "Umbria": "Regione Umbria - BUR",
    "Valle d'Aosta": "Regione Valle d'Aosta - BURVA",
    "Veneto": "Regione Veneto - BURVET",
}


def build_public_snapshot(
    documents: Iterable[LegislativeDocument],
    *,
    previous_payload: Mapping[str, object] | None = None,
    source_statuses: Iterable[Mapping[str, object]] = (),
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Merge newly fetched documents into the complete public catalogue."""

    previous_items = previous_payload.get("documents", []) if previous_payload else []
    items_by_key = {
        str(item["key"]): dict(item)
        for item in previous_items
        if isinstance(item, Mapping) and item.get("key")
    }

    fetched_count = 0
    for document in documents:
        fetched_count += 1
        key = document_identity_key(document)
        items_by_key.pop(key, None)
        item = document_to_public_item(document)
        if item is not None:
            items_by_key[key] = item

    items = sorted(items_by_key.values(), key=_public_item_sort_key, reverse=True)
    generated = (generated_at or datetime.now(UTC)).astimezone(UTC)
    high_count = sum(item.get("relevance") == "Alta" for item in items)
    potential_count = sum(item.get("relevance") == "Potenziale" for item in items)
    source_names = sorted({str(item.get("source")) for item in items if item.get("source")})

    return {
        "schema_version": PUBLIC_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": generated.isoformat().replace("+00:00", "Z"),
        "fetched_document_count": fetched_count,
        "published_document_count": len(items),
        "high_relevance_count": high_count,
        "potential_relevance_count": potential_count,
        "published_source_count": len(source_names),
        "published_sources": source_names,
        "source_statuses": [dict(status) for status in source_statuses],
        "documents": items,
    }


def document_to_public_item(document: LegislativeDocument) -> dict[str, object] | None:
    """Return a display-ready record when an act passes the dashboard rules."""

    if "trova norme salute" in document.source.lower():
        from app.connectors.trovanorme_salute import is_ministry_health_document_relevant

        # Older stored rows may contain only the search term in their summary.
        # Require the visible act title itself to carry a thematic signal.
        if not is_ministry_health_document_relevant(document.title, document.title):
            return None

    score = score_document(document)
    taxonomy = classify_taxonomy(document)
    row = {
        "title": document.title,
        "summary": document.summary,
        "text": document.text,
        "source": document.source,
        "source_type": document.source_type,
        "level": document.level,
        "region": document.region or "",
        "act_type": document.act_type,
        "score": score.total_score,
        "found_terms": score.found_terms,
    }
    if is_excluded_noise_document(row):
        return None
    relevant = is_relevant_primary_document(row)
    potential = is_potential_primary_document(row)
    if not relevant and not potential:
        return None

    primary_date = document.date_published or document.date_presented
    summary = clean_display_text(document.summary or "")
    if not summary:
        summary = _summary_from_text(document.text, document.title)
    identifier = clean_display_text(document.identifier or "")
    key = document_identity_key(document)
    return {
        "key": key,
        "id": identifier or key[:12],
        "identifier": identifier,
        "title": clean_display_text(document.title),
        "source": _public_source_name(document),
        "source_detail": clean_display_text(document.source),
        "kind": document_type_label(row),
        "date": primary_date.isoformat() if primary_date else "",
        "updated_at": _format_datetime(document.last_update),
        "href": str(document.url or ""),
        "relevance": "Alta" if relevant else "Potenziale",
        "topics": [TOPIC_LABELS.get(topic, topic.replace("_", " ").title()) for topic in taxonomy.domains],
        "summary": summary,
        "level": document.level,
        "region": clean_display_text(document.region or ""),
        "status": document.status,
        "score": score.total_score,
        "found_terms": score.found_terms,
    }


def load_public_snapshot(path: str | Path) -> dict[str, object] | None:
    target = Path(path)
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != PUBLIC_SNAPSHOT_SCHEMA_VERSION:
        return None
    return payload


def write_public_snapshot(payload: Mapping[str, object], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        temporary.write_text(serialized, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def _public_source_name(document: LegislativeDocument) -> str:
    source = clean_display_text(document.source)
    if document.level == "regionale" and document.region in REGIONAL_SOURCE_NAMES:
        return REGIONAL_SOURCE_NAMES[str(document.region)]
    source_lower = source.lower()
    mappings = [
        ("camera dei deputati", "Camera dei deputati"),
        ("senato della repubblica", "Senato della Repubblica"),
        ("gazzetta ufficiale", "Gazzetta Ufficiale"),
        ("normattiva", "Normattiva"),
        ("parlamento italiano", "Normattiva"),
        ("ministero della salute", "Ministero della Salute"),
        ("eur-lex", "EUR-Lex"),
        ("agenas", "AGENAS"),
        ("cnop", "CNOP"),
        ("enpap", "ENPAP"),
        ("conferenza stato-regioni", "Conferenza Stato-Regioni"),
        ("garante per la protezione", "Garante per la protezione dei dati personali"),
    ]
    for marker, label in mappings:
        if marker in source_lower:
            return label
    return source


def _summary_from_text(text: str, title: str, *, limit: int = 420) -> str:
    cleaned = clean_display_text(text)
    clean_title = clean_display_text(title)
    if cleaned.startswith(clean_title):
        cleaned = cleaned[len(clean_title) :].strip(" -:\n")
    if not cleaned:
        return "Atto incluso dal monitor in base ai riferimenti tematici rilevati."
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "..."


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _public_item_sort_key(item: Mapping[str, object]) -> tuple[str, str, str]:
    raw_date = str(item.get("date") or "")
    try:
        parsed_date = date.fromisoformat(raw_date).isoformat()
    except ValueError:
        parsed_date = ""
    return parsed_date, str(item.get("updated_at") or ""), str(item.get("id") or "")
