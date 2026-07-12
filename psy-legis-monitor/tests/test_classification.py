from app.core.schemas import LegislativeDocument
from app.core.taxonomy import classify_taxonomy


def test_taxonomy_classification_maps_keywords_to_domains():
    document = LegislativeDocument(
        source="Mock",
        source_type="mock",
        level="nazionale",
        act_type="regolamento",
        identifier="AI-1",
        title="Intelligenza artificiale e dati sanitari",
        status="pubblicato",
        url="https://example.org/ai",
        text="Regole su intelligenza artificiale, telemedicina, privacy e dati sanitari.",
    )

    result = classify_taxonomy(document)

    assert "intelligenza_artificiale_tecnologie_psicologiche" in result.domains
    assert "privacy_dati_sanitari_sanita_digitale" in result.domains

