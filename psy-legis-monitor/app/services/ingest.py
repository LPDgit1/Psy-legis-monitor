"""Ingestion service for connector documents."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import models
from app.core.change_detection import detect_document_change
from app.core.hashing import document_identity_key, stable_text_hash
from app.core.schemas import LegislativeDocument
from app.core.scoring import score_document
from app.core.taxonomy import classify_taxonomy
from app.services.alerting import build_alert


@dataclass
class IngestSummary:
    seen: int = 0
    created: int = 0
    updated: int = 0
    events: int = 0
    alerts: int = 0


def _schema_from_orm(document: models.Document) -> LegislativeDocument:
    return LegislativeDocument(
        source=document.source,
        source_type=document.source_type,
        level=document.level,
        region=document.region,
        act_type=document.act_type,
        identifier=document.identifier,
        title=document.title,
        summary=document.summary,
        date_presented=document.date_presented,
        date_published=document.date_published,
        last_update=document.last_update,
        status=document.status,
        url=document.url,
        text=document.text,
        metadata=document.metadata_json or {},
    )


def _apply_document_fields(target: models.Document, document: LegislativeDocument, text_hash: str) -> None:
    target.source = document.source
    target.source_type = document.source_type
    target.level = document.level
    target.region = document.region
    target.act_type = document.act_type
    target.identifier = document.identifier
    target.title = document.title
    target.summary = document.summary
    target.date_presented = document.date_presented
    target.date_published = document.date_published
    target.last_update = document.last_update
    target.status = document.status
    target.url = str(document.url) if document.url else None
    target.text = document.text
    target.text_hash = text_hash
    target.metadata_json = document.metadata


def upsert_document(session: Session, document: LegislativeDocument) -> IngestSummary:
    summary = IngestSummary(seen=1)
    document_key = document_identity_key(document)
    text_hash = stable_text_hash(document.text)
    existing = session.execute(
        select(models.Document).where(models.Document.document_key == document_key)
    ).scalar_one_or_none()

    if existing is None:
        orm_document = models.Document(document_key=document_key, text_hash=text_hash)
        _apply_document_fields(orm_document, document, text_hash)
        session.add(orm_document)
        session.flush()
        session.add(
            models.DocumentVersion(
                document_id=orm_document.id,
                version_number=1,
                text_hash=text_hash,
                text=document.text,
                source_last_update=document.last_update,
            )
        )
        change = detect_document_change(document)
        summary.created = 1
    else:
        before = _schema_from_orm(existing)
        change = detect_document_change(document, before, existing_text_hash=existing.text_hash)
        if change.events:
            if change.text_changed:
                next_version = len(existing.versions) + 1
                session.add(
                    models.DocumentVersion(
                        document_id=existing.id,
                        version_number=next_version,
                        text_hash=text_hash,
                        text=document.text,
                        source_last_update=document.last_update,
                    )
                )
            _apply_document_fields(existing, document, text_hash)
            summary.updated = 1
        orm_document = existing

    for event in change.events:
        session.add(
            models.LegislativeEvent(
                document_id=orm_document.id,
                event_type=event.event_type,
                summary=event.summary,
                before_json=event.before,
                after_json=event.after,
            )
        )
    summary.events = len(change.events)

    score = score_document(document)
    taxonomy = classify_taxonomy(document)
    session.add(
        models.RelevanceAssessment(
            document_id=orm_document.id,
            score=score.total_score,
            relevance_class=score.relevance_class,
            category_scores=score.category_scores,
            found_terms=score.found_terms,
            domains=taxonomy.domains,
            method="keyword_rules",
            explanation="Punteggio preliminare basato su keywords.yml e taxonomy.yml.",
        )
    )
    alert = build_alert(document, score, taxonomy)
    if alert:
        session.add(
            models.Alert(
                document_id=orm_document.id,
                level=alert.level,
                reason=alert.reason,
                domains=alert.domains,
                recommended_action=alert.recommended_action,
                status=alert.status,
                generated_at=alert.generated_at,
            )
        )
        summary.alerts = 1

    return summary


def ingest_documents(
    session: Session,
    documents: list[LegislativeDocument],
    *,
    commit: bool = True,
) -> IngestSummary:
    total = IngestSummary()
    for document in documents:
        partial = upsert_document(session, document)
        total.seen += partial.seen
        total.created += partial.created
        total.updated += partial.updated
        total.events += partial.events
        total.alerts += partial.alerts
    if commit:
        session.commit()
    return total

