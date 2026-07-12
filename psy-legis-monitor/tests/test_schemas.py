import pytest
from pydantic import ValidationError

from app.core.schemas import LegislativeDocument


def test_legislative_document_validation_accepts_minimum_valid_payload():
    document = LegislativeDocument(
        source="Normattiva",
        source_type="mock",
        level="nazionale",
        act_type="legge",
        identifier="L-1",
        title="Legge di esempio",
        status="pubblicato",
        url="https://example.org/l-1",
        text="Testo della legge.",
        metadata={"numero": "1"},
    )

    assert document.metadata["numero"] == "1"


def test_legislative_document_rejects_blank_text():
    with pytest.raises(ValidationError):
        LegislativeDocument(
            source="Normattiva",
            source_type="mock",
            level="nazionale",
            act_type="legge",
            title="Legge di esempio",
            text=" ",
        )

