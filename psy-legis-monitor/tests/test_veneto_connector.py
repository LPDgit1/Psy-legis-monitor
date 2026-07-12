from datetime import UTC, datetime

from app.connectors.regions import veneto
from app.core.schemas import LegislativeDocument


def test_veneto_connector_keeps_configured_pages_when_bur_is_unreachable(monkeypatch):
    fallback_document = LegislativeDocument(
        source="Regione Veneto - Normativa",
        source_type="html",
        level="regionale",
        region="Veneto",
        act_type="altro",
        identifier="https://www.regione.veneto.it/normativa",
        title="Legge regionale su servizi sociosanitari",
        status="pubblicato",
        url="https://www.regione.veneto.it/normativa",
        text="Legge regionale su servizi sociosanitari",
        last_update=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )

    def failing_fetch(*args, **kwargs):
        raise RuntimeError("BUR non raggiungibile")

    class FakeConfiguredPages:
        def fetch_documents(self):
            return [fallback_document]

    monkeypatch.setattr(veneto, "fetch_text", failing_fetch)
    monkeypatch.setattr(veneto, "_VenetoConfiguredPages", FakeConfiguredPages)

    documents = veneto.VenetoConnector().fetch_documents()

    assert documents == [fallback_document]
