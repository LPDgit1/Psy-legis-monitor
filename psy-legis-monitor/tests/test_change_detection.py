from app.core.change_detection import detect_document_change
from app.core.schemas import LegislativeDocument


def _document(text: str = "Testo iniziale", status: str = "presentato") -> LegislativeDocument:
    return LegislativeDocument(
        source="Senato",
        source_type="mock",
        level="nazionale",
        act_type="disegno_di_legge",
        identifier="AS-1",
        title="Documento",
        status=status,
        url="https://example.org/as-1",
        text=text,
        metadata={"commissione": "Sanita"},
    )


def test_detects_new_document():
    result = detect_document_change(_document())

    assert result.is_new is True
    assert result.events[0].event_type == "new_document"


def test_detects_text_change():
    existing = _document()
    incoming = _document(text="Testo modificato")

    result = detect_document_change(incoming, existing)

    assert result.text_changed is True
    assert any(event.event_type == "text_changed" for event in result.events)


def test_detects_status_change():
    existing = _document(status="presentato")
    incoming = _document(status="approvato")

    result = detect_document_change(incoming, existing)

    assert result.status_changed is True
    assert any(event.event_type == "became_law" for event in result.events)

