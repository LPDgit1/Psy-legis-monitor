from datetime import datetime

import pytest

from app.connectors.page import SourceUnavailableError, parse_page_documents


def test_page_connector_uses_nearby_heading_for_generic_links():
    html = """
    <section>
      <h3>Report della seduta della Conferenza Stato-Regioni del 7 luglio 2026</h3>
      <a href="/it/notizie/report-7-luglio-2026/">SCOPRI TUTTO</a>
    </section>
    <a href="/privacy">Privacy</a>
    """
    config = {
        "name": "Conferenza Stato-Regioni - Notizie",
        "source": "Conferenza Stato-Regioni",
        "level": "nazionale",
        "act_type": "altro",
        "status": "pubblicato",
        "include_patterns": ["Conferenza Stato-Regioni", "Report della seduta"],
        "exclude_patterns": ["Privacy"],
    }

    documents = parse_page_documents(
        html,
        "https://www.statoregioni.it/it/",
        source_config=config,
        fetched_at=datetime(2026, 7, 11, 12, 0),
    )

    assert len(documents) == 1
    assert documents[0].title == "Report della seduta della Conferenza Stato-Regioni del 7 luglio 2026"
    assert documents[0].url == "https://www.statoregioni.it/it/notizie/report-7-luglio-2026/"


def test_page_connector_rejects_gcore_technical_block_page():
    html = """
    <html>
      <head><title>Gcore</title></head>
      <body><script>var sbbgscc='blocked';</script></body>
    </html>
    """

    with pytest.raises(SourceUnavailableError, match="Gcore"):
        parse_page_documents(
            html,
            "https://www.salute.gov.it/new/it/sezione/norme-e-atti/",
            source_config={"include_patterns": ["decreto"]},
            fetched_at=datetime(2026, 7, 12, 12, 0),
        )


def test_conferenza_news_requires_psychology_relevance_terms():
    config = {
        "name": "Conferenza Stato-Regioni - Notizie",
        "source": "Conferenza Stato-Regioni",
        "level": "nazionale",
        "act_type": "altro",
        "status": "pubblicato",
        "include_patterns": [
            "salute mentale",
            "psicolog",
            "consultori",
            "dipendenze",
            "neuropsichiatria",
            "disturbi alimentari",
            "disturbi della nutrizione",
            "autismo",
            "disabilita",
            "disagio psicologico",
        ],
        "exclude_patterns": ["Privacy"],
    }

    generic_html = """
    <section>
      <h3>Report della seduta della Conferenza Stato-Regioni del 7 luglio 2026</h3>
      <a href="/it/notizie/report-7-luglio-2026/">SCOPRI TUTTO</a>
    </section>
    """
    relevant_html = """
    <section>
      <h3>Report della seduta su salute mentale territoriale e consultori</h3>
      <a href="/it/notizie/salute-mentale-consultori/">SCOPRI TUTTO</a>
    </section>
    """

    assert (
        parse_page_documents(
            generic_html,
            "https://www.statoregioni.it/it/",
            source_config=config,
            fetched_at=datetime(2026, 7, 12, 12, 0),
        )
        == []
    )

    documents = parse_page_documents(
        relevant_html,
        "https://www.statoregioni.it/it/",
        source_config=config,
        fetched_at=datetime(2026, 7, 12, 12, 0),
    )

    assert len(documents) == 1
    assert documents[0].title == "Salute mentale consultori"


def test_garante_news_filters_generic_press_items_but_keeps_health_privacy():
    config = {
        "name": "Garante Privacy - Home",
        "source": "Garante per la protezione dei dati personali",
        "level": "nazionale",
        "act_type": "altro",
        "status": "pubblicato",
        "include_patterns": [
            "dati sanitari",
            "dati relativi alla salute",
            "fascicolo sanitario",
            "telemedicina",
            "salute mentale",
            "psicolog",
            "psicoterapia",
        ],
        "exclude_patterns": [
            "Cookie",
            "Privacy e Cookie",
            "^Linee guida$",
            "^Newsletter$",
            "^Infografiche e vademecum$",
            "comunicato stampa",
            "newsletter",
            "audizione",
        ],
    }

    generic_html = """
    <section>
      <a href="/home/docweb/-/docweb-display/docweb/123">
        COMUNICATO STAMPA - Newsletter n. 527
      </a>
    </section>
    """
    relevant_html = """
    <section>
      <a href="/home/docweb/-/docweb-display/docweb/456">
        Fascicolo sanitario elettronico e dati sanitari: indicazioni del Garante
      </a>
    </section>
    """

    assert (
        parse_page_documents(
            generic_html,
            "https://www.garanteprivacy.it/",
            source_config=config,
            fetched_at=datetime(2026, 7, 12, 12, 0),
        )
        == []
    )

    documents = parse_page_documents(
        relevant_html,
        "https://www.garanteprivacy.it/",
        source_config=config,
        fetched_at=datetime(2026, 7, 12, 12, 0),
    )

    assert len(documents) == 1
    assert "dati sanitari" in documents[0].title.lower()
