"""Markdown report generation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _doc_block(document: Any, reason: str | None = None, action: str | None = None) -> str:
    title = _value(document, "title", "Senza titolo")
    source = _value(document, "source", "Fonte non disponibile")
    status = _value(document, "status", "sconosciuto")
    url = _value(document, "url", "")
    lines = [
        f"* Titolo: {title}",
        f"  Fonte: {source}",
        f"  Stato: {status}",
    ]
    if reason:
        lines.append(f"  Perché rilevante: {reason}")
    if action:
        lines.append(f"  Azione suggerita: {action}")
    if url:
        lines.append(f"  Link: {url}")
    return "\n".join(lines)


def generate_weekly_report(
    documents: Sequence[Any],
    *,
    alerts: Sequence[Any] | None = None,
    changed_documents: Sequence[Any] | None = None,
    false_positive_candidates: Sequence[Any] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> str:
    today = date.today()
    start = period_start or (today - timedelta(days=7))
    end = period_end or today
    alerts = alerts or []
    changed_documents = changed_documents or []
    false_positive_candidates = false_positive_candidates or []

    red = [alert for alert in alerts if _value(alert, "level") == "rosso"]
    orange = [alert for alert in alerts if _value(alert, "level") == "arancione"]
    blue = [alert for alert in alerts if _value(alert, "level") == "blu"]

    lines = [
        "# Report settimanale monitoraggio normativo psicologia",
        "",
        f"Periodo: {start.isoformat()} / {end.isoformat()}",
        "",
        "## Sintesi esecutiva",
        "",
        f"Sono stati individuati {len(documents)} nuovi atti potenzialmente rilevanti.",
        f"{len(red)} atti presentano priorità alta.",
        f"{len(orange) + len(blue)} atti richiedono monitoraggio.",
        "",
        "## Nuovi atti rilevanti",
        "",
    ]
    lines.extend(_doc_block(document) for document in documents)
    if not documents:
        lines.append("Nessun nuovo atto rilevante nel periodo.")

    lines.extend(["", "## Atti modificati", ""])
    lines.extend(_doc_block(document) for document in changed_documents)
    if not changed_documents:
        lines.append("Nessuna modifica rilevante rilevata.")

    for title, group in [
        ("Alert rossi", red),
        ("Alert arancioni", orange),
        ("Alert blu", blue),
    ]:
        lines.extend(["", f"## {title}", ""])
        if not group:
            lines.append("Nessun alert.")
        for alert in group:
            lines.append(
                _doc_block(
                    alert,
                    reason=_value(alert, "reason"),
                    action=_value(alert, "recommended_action"),
                )
            )

    lines.extend(["", "## Atti archiviabili o falsi positivi", ""])
    if false_positive_candidates:
        lines.extend(_doc_block(document) for document in false_positive_candidates)
    else:
        lines.append("Nessun candidato segnalato.")

    lines.extend(["", "## Azioni suggerite", ""])
    actions = sorted({_value(alert, "recommended_action") for alert in alerts if _value(alert, "recommended_action")})
    lines.extend(f"* {action}" for action in actions) if actions else lines.append("* Monitoraggio ordinario.")

    lines.extend(["", "## Elenco link ufficiali", ""])
    links = [str(_value(document, "url")) for document in documents if _value(document, "url")]
    lines.extend(f"* {link}" for link in links) if links else lines.append("Nessun link disponibile.")

    return "\n".join(lines) + "\n"

