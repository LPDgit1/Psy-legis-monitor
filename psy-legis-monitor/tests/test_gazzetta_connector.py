from datetime import datetime

from app.connectors.gazzetta import (
    GazzettaSeriesConfig,
    parse_issue_documents,
    parse_issue_links,
)


def test_parse_issue_links_extracts_detail_urls():
    html = """
    <html><body>
      <a href="/gazzetta/serie_generale/caricaDettaglio?dataPubblicazioneGazzetta=2026-06-10&numeroGazzetta=132">
        n° 132 del 10-06-2026
      </a>
      <a href="/resources/file.pdf">Download PDF</a>
    </body></html>
    """

    links = parse_issue_links(html, "https://www.gazzettaufficiale.it/30giorni/serie_generale")

    assert links == [
        "https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio?dataPubblicazioneGazzetta=2026-06-10&numeroGazzetta=132"
    ]


def test_parse_issue_documents_maps_acts_to_legislative_documents():
    html = """
    <html><body>
      Serie Generale n. 132 del 10-6-2026
      <a href="/atto/serie_generale/caricaDettaglioAtto?atto.codiceRedazionale=26A00001">
        DECRETO 1 giugno 2026
      </a>
      <a href="/atto/serie_generale/caricaDettaglioAtto?atto.codiceRedazionale=26A00001">
        Misure per servizi territoriali, salute mentale e consultori.
      </a>
    </body></html>
    """
    config = GazzettaSeriesConfig(
        name="Serie Generale",
        list_url="https://www.gazzettaufficiale.it/30giorni/serie_generale",
        source="Gazzetta Ufficiale - Serie Generale",
        level="nazionale",
    )

    documents = parse_issue_documents(
        html,
        "https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio?dataPubblicazioneGazzetta=2026-06-10&numeroGazzetta=132",
        series_config=config,
        fetched_at=datetime(2026, 6, 10, 12, 0),
    )

    assert len(documents) == 1
    assert documents[0].identifier == "26A00001"
    assert documents[0].date_published.isoformat() == "2026-06-10"
    assert documents[0].source == "Gazzetta Ufficiale - Serie Generale"
    assert "salute mentale" in documents[0].summary


def test_parse_issue_documents_infers_region_from_regional_issue_context():
    html = """
    <html><body>
      3ª Serie Speciale - Regioni n. 27 del 10-6-2026
      <p>REGIONE LAZIO</p>
      <a href="/atto/3serie/caricaDettaglioAtto?atto.codiceRedazionale=26R00001">
        LEGGE REGIONALE 1 giugno 2026
      </a>
      <a href="/atto/3serie/caricaDettaglioAtto?atto.codiceRedazionale=26R00001">
        Disposizioni in materia di psicologia scolastica.
      </a>
    </body></html>
    """
    config = GazzettaSeriesConfig(
        name="3a Serie Speciale - Regioni",
        list_url="https://www.gazzettaufficiale.it/30giorni/3a_serie_speciale",
        source="Gazzetta Ufficiale - 3a Serie Speciale Regioni",
        level="regionale",
    )

    documents = parse_issue_documents(
        html,
        "https://www.gazzettaufficiale.it/gazzetta/3a_serie_speciale/caricaDettaglio?dataPubblicazioneGazzetta=2026-06-10&numeroGazzetta=27",
        series_config=config,
        fetched_at=datetime(2026, 6, 10, 12, 0),
    )

    assert len(documents) == 1
    assert documents[0].region == "Lazio"
    assert documents[0].act_type == "legge"
