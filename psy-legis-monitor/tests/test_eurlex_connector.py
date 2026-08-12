from app.connectors.eurlex import is_relevant_eurlex_document
from app.core.schemas import LegislativeDocument


def _document(title: str, summary: str = "") -> LegislativeDocument:
    return LegislativeDocument(
        source="EUR-Lex",
        source_type="rss",
        level="europeo",
        act_type="altro",
        title=title,
        summary=summary,
        status="pubblicato",
        url="https://eur-lex.europa.eu/test",
        text=f"{title} {summary}",
    )


def test_eurlex_relevance_keeps_direct_mental_health_act():
    assert is_relevant_eurlex_document(
        _document("Raccomandazione sui servizi di salute mentale per adolescenti")
    )


def test_eurlex_relevance_keeps_combined_health_data_context():
    assert is_relevant_eurlex_document(
        _document("Regolamento sulla tutela dei dati sanitari nei servizi di assistenza sanitaria")
    )


def test_eurlex_relevance_rejects_veterinary_noise():
    assert not is_relevant_eurlex_document(
        _document("Regolamento sui medicinali veterinari e la salute animale")
    )
