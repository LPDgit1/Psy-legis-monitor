from datetime import date

from app.core.schemas import LegislativeDocument
from app.services.reports import generate_weekly_report


def test_generate_weekly_report_contains_required_sections():
    document = LegislativeDocument(
        source="Camera",
        source_type="mock",
        level="nazionale",
        act_type="proposta_di_legge",
        identifier="AC-1",
        title="Psicologo scolastico",
        status="presentato",
        url="https://example.org/ac-1",
        text="Testo su psicologo scolastico.",
    )
    markdown = generate_weekly_report(
        [document],
        alerts=[
            {
                "title": document.title,
                "source": document.source,
                "status": document.status,
                "url": str(document.url),
                "level": "rosso",
                "reason": "Rilevanza diretta.",
                "recommended_action": "proposta_emendamento",
            }
        ],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 7),
    )

    assert "# Report settimanale monitoraggio normativo psicologia" in markdown
    assert "## Alert rossi" in markdown
    assert "Psicologo scolastico" in markdown

