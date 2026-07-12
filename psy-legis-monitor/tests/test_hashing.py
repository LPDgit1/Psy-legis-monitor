from app.core.hashing import document_identity_key, stable_text_hash
from app.core.schemas import LegislativeDocument


def test_stable_text_hash_ignores_whitespace_noise():
    assert stable_text_hash("Testo   con\nspazi") == stable_text_hash("Testo con spazi")


def test_document_identity_prefers_identifier_over_url():
    first = LegislativeDocument(
        source="Camera",
        source_type="mock",
        level="nazionale",
        act_type="proposta_di_legge",
        identifier="AC-1",
        title="Titolo",
        status="presentato",
        url="https://example.org/a",
        text="Testo",
    )
    second = first.model_copy(update={"url": "https://example.org/b"})
    assert document_identity_key(first) == document_identity_key(second)

