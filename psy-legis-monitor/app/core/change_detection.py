"""Deterministic change detection for normalized documents."""

from __future__ import annotations

from typing import Any

from app.core.hashing import document_identity_key, stable_text_hash
from app.core.schemas import (
    ChangeDetectionResult,
    LegislativeDocument,
    LegislativeEvent,
)


def _event(
    document_key: str,
    event_type: str,
    summary: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> LegislativeEvent:
    return LegislativeEvent(
        document_key=document_key,
        event_type=event_type,
        summary=summary,
        before=before or {},
        after=after or {},
    )


def _metadata_subset(metadata: dict[str, Any], keys: set[str] | None) -> dict[str, Any]:
    if keys is None:
        return metadata
    return {key: metadata.get(key) for key in keys if key in metadata}


def detect_document_change(
    incoming: LegislativeDocument,
    existing: LegislativeDocument | None = None,
    *,
    existing_text_hash: str | None = None,
    relevant_metadata_keys: set[str] | None = None,
) -> ChangeDetectionResult:
    """Compare incoming normalized data with a known document snapshot."""

    document_key = document_identity_key(incoming)
    incoming_hash = stable_text_hash(incoming.text)
    if existing is None:
        event = _event(
            document_key,
            "new_document",
            f"Nuovo documento rilevato: {incoming.title}",
            after={"title": incoming.title, "status": incoming.status},
        )
        return ChangeDetectionResult(
            is_new=True,
            events=[event],
            summary="Nuovo documento rilevato.",
        )

    events: list[LegislativeEvent] = []
    known_hash = existing_text_hash or stable_text_hash(existing.text)

    if incoming_hash != known_hash:
        events.append(
            _event(
                document_key,
                "text_changed",
                "Il testo normalizzato del documento e cambiato.",
                before={"text_hash": known_hash},
                after={"text_hash": incoming_hash},
            )
        )

    if incoming.status != existing.status:
        event_type = "became_law" if incoming.status in {"approvato", "pubblicato"} else "status_changed"
        events.append(
            _event(
                document_key,
                event_type,
                f"Stato cambiato da {existing.status} a {incoming.status}.",
                before={"status": existing.status},
                after={"status": incoming.status},
            )
        )

    before_metadata = _metadata_subset(existing.metadata, relevant_metadata_keys)
    after_metadata = _metadata_subset(incoming.metadata, relevant_metadata_keys)
    if before_metadata != after_metadata:
        events.append(
            _event(
                document_key,
                "metadata_changed",
                "Metadata rilevanti modificati.",
                before=before_metadata,
                after=after_metadata,
            )
        )

    if str(incoming.url or "") != str(existing.url or ""):
        events.append(
            _event(
                document_key,
                "url_changed",
                "URL ufficiale modificato.",
                before={"url": str(existing.url or "")},
                after={"url": str(incoming.url or "")},
            )
        )

    event_types = {event.event_type for event in events}
    if events:
        summary = "; ".join(event.summary for event in events)
    else:
        summary = "Nessun cambiamento rilevato."

    return ChangeDetectionResult(
        text_changed="text_changed" in event_types,
        status_changed=bool({"status_changed", "became_law"} & event_types),
        metadata_changed="metadata_changed" in event_types,
        url_changed="url_changed" in event_types,
        events=events,
        summary=summary,
    )

