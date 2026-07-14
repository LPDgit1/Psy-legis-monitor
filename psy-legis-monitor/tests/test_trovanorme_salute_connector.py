from datetime import UTC, datetime

from app.connectors.trovanorme_salute import (
    build_trovanorme_act_document,
    is_ministry_health_document_relevant,
    parse_trovanorme_act_links,
    parse_trovanorme_detail,
    parse_trovanorme_news_links,
)


def test_parse_trovanorme_news_links_extracts_recent_news():
    html = """
    <h2>News norme</h2>
    08 luglio 2026 <a href="/norme/dettaglioNews?id=123">Programma nazionale HTA dispositivi medici 2026-2028</a>
    01 luglio 2026 <a href="/norme/dettaglioNews?id=124">Prestazioni ospedaliere - tariffe massime</a>
    """

    links = parse_trovanorme_news_links(
        html,
        "https://www.trovanorme.salute.gov.it/norme/ricerca",
        max_items=2,
    )

    assert links == [
        (
            "Programma nazionale HTA dispositivi medici 2026-2028",
            "https://www.trovanorme.salute.gov.it/norme/dettaglioNews?id=123",
        ),
        (
            "Prestazioni ospedaliere - tariffe massime",
            "https://www.trovanorme.salute.gov.it/norme/dettaglioNews?id=124",
        ),
    ]


def test_parse_trovanorme_act_links_skips_read_more_duplicates():
    html = """
    <a href="dettaglioAtto?id=111660">Delibera 29/01/2026</a>
    <a href="dettaglioAtto?id=111660">Leggi tutto</a>
    <a href="dettaglioAtto?id=113094">Decreto ministeriale 23/06/2026</a>
    """

    links = parse_trovanorme_act_links(
        html,
        "https://www.trovanorme.salute.gov.it/norme/ricercaAtti?word=psicologo",
        max_items=5,
    )

    assert links == [
        (
            "Delibera 29/01/2026",
            "https://www.trovanorme.salute.gov.it/norme/dettaglioAtto?id=111660",
        ),
        (
            "Decreto ministeriale 23/06/2026",
            "https://www.trovanorme.salute.gov.it/norme/dettaglioAtto?id=113094",
        ),
    ]


def test_parse_trovanorme_act_links_enriches_title_from_result_context():
    html = """
    <ul>
      <li>
        <a href="dettaglioAtto?id=113094">Decreto ministeriale 23/06/2026</a>
        <span>Oggetto: Riparto del Fondo per il contrasto dei disturbi della nutrizione e dell'alimentazione</span>
        <a href="dettaglioAtto?id=113094">Leggi tutto</a>
      </li>
    </ul>
    """

    links = parse_trovanorme_act_links(
        html,
        "https://www.trovanorme.salute.gov.it/norme/ricercaAtti?word=salute+mentale",
        max_items=5,
    )

    assert links == [
        (
            "Riparto del Fondo per il contrasto dei disturbi della nutrizione e dell'alimentazione "
            "(Decreto ministeriale 23/06/2026)",
            "https://www.trovanorme.salute.gov.it/norme/dettaglioAtto?id=113094",
        )
    ]


def test_build_trovanorme_act_document_uses_result_metadata():
    document = build_trovanorme_act_document(
        "Riparto del Fondo per il contrasto dei disturbi della nutrizione e dell'alimentazione "
        "(Decreto ministeriale 23/06/2026)",
        "https://www.trovanorme.salute.gov.it/norme/dettaglioAtto?id=113094",
        search_term="salute mentale",
        fetched_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )

    assert document.date_published.isoformat() == "2026-06-23"
    assert document.act_type == "altro"
    assert document.title.startswith("Riparto del Fondo")
    assert "Atto: Decreto ministeriale 23/06/2026" in document.summary
    assert document.metadata["search_term"] == "salute mentale"


def test_ministry_relevance_rejects_veterinary_false_positive():
    assert not is_ministry_health_document_relevant(
        "Decreto ministeriale sui medicinali veterinari",
        "Autorizzazione all'immissione in commercio di farmaci veterinari per animali",
        search_term="psicologo",
    )


def test_ministry_relevance_rejects_wild_boar_and_epizootic_false_positive():
    assert not is_ministry_health_document_relevant(
        "Ordinanza sulla peste suina africana",
        "Misure veterinarie sui cinghiali, biosicurezza degli allevamenti e fauna selvatica",
        search_term="salute mentale",
    )


def test_ministry_relevance_rejects_fitoterapici_false_positive():
    assert not is_ministry_health_document_relevant(
        "Decreto sui prodotti fitoterapici e omeopatici",
        "Requisiti per la commercializzazione di integratori alimentari e prodotti erboristici",
        search_term="dipendenze",
    )


def test_ministry_relevance_keeps_mental_health_related_act():
    assert is_ministry_health_document_relevant(
        "Riparto del Fondo per il contrasto dei disturbi della nutrizione e dell'alimentazione",
        "Misure per servizi di salute mentale e disturbi alimentari",
        search_term="salute mentale",
    )


def test_parse_trovanorme_detail_builds_legislative_document():
    html = """
    <h2>News</h2>
    <h3>16 giugno 2026 - Salute mentale - decreto ministeriale</h3>
    <p>In G.U. e' pubblicato il decreto 30 aprile 2026 recante misure sui servizi di salute mentale.</p>
    """

    document = parse_trovanorme_detail(
        html,
        "https://www.trovanorme.salute.gov.it/norme/dettaglioNews?id=1",
        fallback_title="Salute mentale",
        fetched_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )

    assert document.source == "Ministero della Salute - Trova Norme Salute"
    assert document.title == "Salute mentale - decreto ministeriale"
    assert document.date_published.isoformat() == "2026-06-16"
    assert document.status == "pubblicato"
    assert "servizi di salute mentale" in document.text
