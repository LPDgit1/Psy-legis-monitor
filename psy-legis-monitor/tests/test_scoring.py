from app.core.schemas import LegislativeDocument
from app.core.scoring import score_document


def test_score_document_detects_direct_psychology_relevance():
    document = LegislativeDocument(
        source="Mock",
        source_type="mock",
        level="nazionale",
        act_type="proposta_di_legge",
        identifier="1",
        title="Istituzione dello psicologo scolastico",
        status="in_commissione",
        url="https://example.org/doc",
        text=(
            "La proposta introduce lo psicologo scolastico, lo sportello psicologico "
            "e consulenza psicologica per studenti e adolescenti."
        ),
    )

    result = score_document(document)

    assert result.relevance_class == "alta"
    assert "servizi_psicologici" in result.found_terms
    assert result.total_score > 0


def test_score_document_detects_psychotherapy_and_counseling_terms():
    document = LegislativeDocument(
        source="Mock",
        source_type="mock",
        level="nazionale",
        act_type="proposta_di_legge",
        identifier="2",
        title="Disposizioni su psicoterapia e counseling psicologico",
        status="presentato",
        url="https://example.org/doc2",
        text=(
            "Il testo disciplina l'accesso a psicoterapia, counseling psicologico "
            "e servizi di salute mentale nei consultori."
        ),
    )

    result = score_document(document)

    assert result.relevance_class in {"alta", "media"}
    assert {"professione_diretta", "servizi_psicologici"} & set(result.found_terms)


def test_score_document_does_not_promote_generic_work_mentions():
    document = LegislativeDocument(
        source="Mock",
        source_type="mock",
        level="nazionale",
        act_type="decreto_legislativo",
        identifier="3",
        title="Liquidazione coatta amministrativa di cooperativa di produzione e lavoro",
        status="pubblicato",
        url="https://example.org/doc3",
        text="Sostituzione del commissario liquidatore della societa cooperativa di lavoro.",
    )

    result = score_document(document)

    assert result.relevance_class == "irrilevante"
