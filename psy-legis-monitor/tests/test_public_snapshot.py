from datetime import UTC, date, datetime

from app.core.schemas import LegislativeDocument
from app.services.public_snapshot import (
    build_public_snapshot,
    document_to_public_item,
    revalidate_public_snapshot,
)


def _document(**overrides) -> LegislativeDocument:
    values = {
        "source": "Camera dei deputati - Dati Camera",
        "source_type": "official_api",
        "level": "nazionale",
        "act_type": "proposta_di_legge",
        "identifier": "C.100",
        "title": "Istituzione del servizio di psicologia scolastica",
        "summary": "Supporto psicologico per studenti e famiglie.",
        "date_presented": date(2026, 8, 10),
        "last_update": datetime(2026, 8, 11, tzinfo=UTC),
        "status": "presentato",
        "url": "https://www.camera.it/atto/100",
        "text": "Istituzione del servizio di psicologia scolastica e supporto psicologico.",
    }
    values.update(overrides)
    return LegislativeDocument(**values)


def test_public_snapshot_includes_every_relevant_and_potential_act():
    direct = _document()
    potential = _document(
        identifier="C.101",
        title="Misure di tutela per adolescenti",
        summary="Interventi rivolti agli adolescenti.",
        text="Misure di tutela rivolte agli adolescenti.",
    )

    payload = build_public_snapshot(
        [direct, potential],
        generated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

    assert payload["published_document_count"] == 2
    assert {item["id"] for item in payload["documents"]} == {"C.100", "C.101"}
    assert payload["high_relevance_count"] == 1
    assert payload["potential_relevance_count"] == 1


def test_public_snapshot_rejects_known_ministry_noise():
    noise = _document(
        source="Ministero della Salute - Trova Norme Salute",
        source_type="html",
        act_type="altro",
        identifier="MS-1",
        title="Misure per la peste suina africana e le carcasse di cinghiale",
        summary="Provvedimenti veterinari per animali selvatici.",
        text="Peste suina africana, veterinaria, cinghiali e carcasse.",
    )

    assert document_to_public_item(noise) is None


def test_public_snapshot_rejects_regional_enology_school_noise():
    noise = _document(
        source="Abruzzo BUR",
        source_type="pdf",
        level="regionale",
        region="Abruzzo",
        act_type="dgr",
        identifier="BUR-Abruzzo-1",
        title="Criteri per l'accreditamento di un istituto scolastico enologico e vitivinicolo",
        summary="Requisiti organizzativi dell'istituto scolastico.",
        text="Accreditamento e requisiti organizzativi dell'istituto scolastico.",
    )

    assert document_to_public_item(noise) is None


def test_public_snapshot_rejects_regional_weak_repetition():
    weak = _document(
        source="Abruzzo BUR",
        source_type="pdf",
        level="regionale",
        region="Abruzzo",
        act_type="dgr",
        identifier="BUR-Abruzzo-2",
        title="Bollettino ufficiale regionale - PSIC",
        summary="Scuola e famiglia.",
        text="Scuola e famiglia. " * 40,
    )

    assert document_to_public_item(weak) is None


def test_public_snapshot_revalidates_previous_noise_items():
    stale = {
        "key": "stale-enology",
        "id": "26A03818",
        "identifier": "26A03818",
        "title": (
            "DECRETO 24 luglio 2026 - Rinnovo della designazione al Laboratorio "
            "enochimico Ex allievi Scuola enologica Conegliano nel settore vitivinicolo"
        ),
        "source": "Gazzetta Ufficiale",
        "source_detail": "Gazzetta Ufficiale - Serie Generale",
        "kind": "Atto normativo",
        "relevance": "Potenziale",
        "level": "nazionale",
        "region": "",
        "score": 3.36,
        "found_terms": {"scuola_minori_famiglia": ["scuola"]},
    }

    payload = revalidate_public_snapshot(
        {
            "schema_version": 1,
            "fetched_document_count": 76,
            "documents": [stale],
        },
        generated_at=datetime(2026, 8, 27, tzinfo=UTC),
    )

    assert payload["fetched_document_count"] == 76
    assert payload["published_document_count"] == 0
    assert payload["documents"] == []


def test_public_snapshot_rejects_ministry_search_provenance_without_title_signal():
    generic = _document(
        source="Ministero della Salute - Trova Norme Salute",
        source_type="html",
        act_type="altro",
        identifier="MS-2",
        title="Decreto ministeriale 23/06/2026",
        summary="Risultato Trova Norme Salute per: dipendenze",
        text="Decreto ministeriale 23/06/2026. Risultato Trova Norme Salute per: dipendenze",
    )

    assert document_to_public_item(generic) is None


def test_public_snapshot_keeps_older_items_and_replaces_refetched_rows():
    original = _document()
    first = build_public_snapshot(
        [original],
        generated_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    added = _document(identifier="C.102", title="Psicologi nelle cure primarie")
    updated = _document(title="Istituzione stabile del servizio di psicologia scolastica")

    merged = build_public_snapshot(
        [updated, added],
        previous_payload=first,
        generated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

    assert merged["published_document_count"] == 2
    titles = {item["id"]: item["title"] for item in merged["documents"]}
    assert titles["C.100"] == "Istituzione stabile del servizio di psicologia scolastica"
    assert "C.102" in titles


def test_public_snapshot_normalizes_regional_source_name():
    regional = _document(
        source="Gazzetta Ufficiale - 3a Serie Speciale Regioni",
        source_type="html",
        level="regionale",
        region="Lazio",
        act_type="legge",
        identifier="L.R. 10/2026",
    )

    item = document_to_public_item(regional)

    assert item is not None
    assert item["source"] == "Regione Lazio - BUR"
