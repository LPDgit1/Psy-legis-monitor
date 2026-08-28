from datetime import UTC, datetime

import pytest

from app.connectors.regions.bur import (
    RegionalBurConnector,
    RegionalBurSource,
    find_recent_detail_links,
    find_recent_pdf_links,
    is_relevant_regional_candidate,
    is_relevant_regional_act,
    load_regional_bur_sources,
    parse_regional_bur_html,
    parse_regional_bur_pdf,
    _has_meaningful_regional_title,
)


def _source() -> RegionalBurSource:
    return RegionalBurSource(
        name="Regione Lazio - BUR",
        region="Lazio",
        url="https://example.test/bur",
        adapter="html",
    )


def test_regional_bur_registry_covers_all_twenty_regions():
    sources = load_regional_bur_sources()

    assert len(sources) == 20
    assert len({source.region for source in sources}) == 20
    assert {source.adapter for source in sources} <= {"html", "html_pdf", "veneto"}
    assert all(source.max_items == 20 for source in sources)
    assert all(source.max_detail_links == 3 for source in sources)
    assert all(source.max_pdf_links == 2 for source in sources)
    assert all(source.max_pdf_pages == 16 for source in sources)


def test_regional_html_parser_keeps_relevant_normative_act():
    html = """
    <article>
      <h2>DELIBERAZIONE DELLA GIUNTA REGIONALE 12/08/2026</h2>
      <p>Rafforzamento dei servizi di psicologia nei consultori familiari.</p>
      <a href="/atti/123">Consulta l'atto</a>
    </article>
    """

    documents = parse_regional_bur_html(
        html,
        "https://example.test/bur",
        source=_source(),
        fetched_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

    assert len(documents) == 1
    assert documents[0].region == "Lazio"
    assert documents[0].act_type == "dgr"
    assert str(documents[0].url) == "https://example.test/atti/123"


def test_regional_html_parser_rejects_veterinary_noise():
    html = """
    <article>
      <h2>DECRETO 12/08/2026</h2>
      <p>Controllo della peste suina africana e delle popolazioni di cinghiali.</p>
      <a href="/atti/456">Consulta l'atto</a>
    </article>
    """

    documents = parse_regional_bur_html(
        html,
        "https://example.test/bur",
        source=_source(),
        fetched_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

    assert documents == []


def test_regional_relevance_requires_direct_signal_or_two_contexts():
    assert is_relevant_regional_act("Legge regionale sullo psicologo di base")
    assert is_relevant_regional_act("Servizi sanitari per minori e famiglie")
    assert not is_relevant_regional_act("Disciplina generale della viabilita regionale")


def test_regional_relevance_rejects_educational_wine_and_viticulture_noise():
    assert not is_relevant_regional_act(
        "Criteri per l'accreditamento di un istituto scolastico enologico e vitivinicolo"
    )


def test_regional_relevance_rejects_disability_parking_without_psychological_context():
    assert not is_relevant_regional_act(
        "Disposizioni per il rinnovo del contrassegno europeo di parcheggio per le persone con disabilita"
    )
    assert is_relevant_regional_act(
        "Servizi di riabilitazione e presa in carico delle persone con disabilita"
    )


def test_regional_title_validation_rejects_header_only_fragments():
    assert not _has_meaningful_regional_title("DETERMINAZIONE N.")
    assert not _has_meaningful_regional_title(
        "deliberazione, il Dirigente del Servizio e il Direttore del Dipartimento competente"
    )
    assert _has_meaningful_regional_title(
        "DELIBERAZIONE DELLA GIUNTA REGIONALE 2/2026 - Servizi di supporto psicologico"
    )


def test_regional_candidate_does_not_use_distant_incidental_text():
    distant = "Bollettino ufficiale regionale. " + ("testo amministrativo " * 180)
    distant += " psicologia "
    assert not is_relevant_regional_candidate(
        "Criteri per l'accreditamento di un istituto scolastico", distant
    )


def test_regional_candidate_keeps_a_relevant_act_heading():
    assert is_relevant_regional_candidate(
        "Servizi di supporto psicologico nei consultori regionali",
        "Deliberazione regionale per la presa in carico e il supporto alle persone.",
    )


def test_regional_pdf_parser_ignores_cover_and_distant_incidental_keyword(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [
                FakePage("Indice del Bollettino regionale. PSIC"),
                FakePage(
                    "DELIBERAZIONE DELLA GIUNTA REGIONALE 1/2026 "
                    + ("testo amministrativo " * 180)
                    + " psicologia"
                ),
            ]

    monkeypatch.setattr("app.connectors.regions.bur.PdfReader", FakeReader)

    assert parse_regional_bur_pdf(
        b"pdf",
        "https://example.test/bur/numero-1.pdf",
        source=_source(),
        fetched_at=datetime(2026, 8, 12, tzinfo=UTC),
    ) == []


def test_regional_pdf_parser_keeps_relevant_act_after_cover(monkeypatch):
    class FakePage:
        def extract_text(self):
            return (
                "DELIBERAZIONE DELLA GIUNTA REGIONALE 2/2026 "
                "Servizi di supporto psicologico nei consultori familiari."
            )

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [FakePage()]

    monkeypatch.setattr("app.connectors.regions.bur.PdfReader", FakeReader)

    documents = parse_regional_bur_pdf(
        b"pdf",
        "https://example.test/bur/numero-2.pdf",
        source=_source(),
        fetched_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

    assert len(documents) == 1
    assert "supporto psicologico" in documents[0].title.lower()


def test_recent_pdf_links_are_absolute_and_deduplicated():
    html = """
    <a href="/bur/numero-10.pdf">Scarica PDF</a>
    <a href="/bur/numero-10.pdf">Download</a>
    <a href="/bur/numero-9.pdf">Numero precedente</a>
    """

    assert find_recent_pdf_links(html, "https://example.test/bur") == [
        "https://example.test/bur/numero-10.pdf",
        "https://example.test/bur/numero-9.pdf",
    ]


def test_recent_detail_links_find_issue_pages_without_pdfs():
    html = """
    <a href="/bur/ordinario-32-2026">Ordinario n. 32/2026</a>
    <a href="/bur/ordinario-32-2026">Apri bollettino</a>
    <a href="/bur/numero-31.pdf">Bollettino precedente</a>
    """

    assert find_recent_detail_links(html, "https://example.test/bur") == [
        "https://example.test/bur/ordinario-32-2026"
    ]


def test_regional_connector_isolates_one_source_failure(monkeypatch):
    sources = [
        RegionalBurSource(name="Abruzzo BUR", region="Abruzzo", url="https://example.test/a"),
        RegionalBurSource(name="Lazio BUR", region="Lazio", url="https://example.test/b"),
    ]
    connector = RegionalBurConnector(sources)

    def fake_fetch(source):
        if source.region == "Abruzzo":
            raise RuntimeError("temporaneamente indisponibile")
        return []

    monkeypatch.setattr(connector, "_fetch_source", fake_fetch)

    assert connector.fetch_documents() == []
    assert [status.status for status in connector.last_statuses] == [
        "error",
        "reachable_no_relevant_results",
    ]


def test_regional_connector_raises_when_every_source_fails(monkeypatch):
    connector = RegionalBurConnector(
        [RegionalBurSource(name="Abruzzo BUR", region="Abruzzo", url="https://example.test/a")]
    )
    monkeypatch.setattr(
        connector,
        "_fetch_source",
        lambda source: (_ for _ in ()).throw(RuntimeError("non disponibile")),
    )

    with pytest.raises(RuntimeError, match="Nessuno dei BUR"):
        connector.fetch_documents()
