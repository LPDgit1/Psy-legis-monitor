"""Pydantic schemas for normalized legislative intelligence data."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


SourceType = Literal["official_api", "rss", "html", "pdf", "manual", "mock"]
Level = Literal["nazionale", "regionale", "europeo", "locale"]
ActType = Literal[
    "disegno_di_legge",
    "proposta_di_legge",
    "legge",
    "decreto_legge",
    "decreto_legislativo",
    "regolamento",
    "dgr",
    "bur",
    "altro",
]
DocumentStatus = Literal[
    "presentato",
    "assegnato",
    "in_commissione",
    "approvato",
    "pubblicato",
    "decaduto",
    "sconosciuto",
]
RelevanceClass = Literal["alta", "media", "bassa", "irrilevante"]
EventType = Literal[
    "new_document",
    "text_changed",
    "status_changed",
    "metadata_changed",
    "url_changed",
    "became_law",
    "archived_or_inactive",
]
AlertLevel = Literal["rosso", "arancione", "blu"]
AlertStatus = Literal["nuovo", "letto", "validato", "falso_positivo", "archiviato"]
RecommendedAction = Literal[
    "nessuna_azione",
    "monitoraggio",
    "richiesta_chiarimenti",
    "nota_tecnica",
    "interlocuzione_politica",
    "proposta_emendamento",
    "comunicato",
    "audizione",
    "segnalazione_CNOP",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


class LegislativeDocument(BaseModel):
    """Normalized representation of an act from any supported source."""

    model_config = ConfigDict(extra="forbid")

    source: str
    source_type: SourceType
    level: Level
    region: str | None = None
    act_type: ActType
    identifier: str | None = None
    title: str
    summary: str | None = None
    date_presented: date | None = None
    date_published: date | None = None
    last_update: datetime | None = None
    status: DocumentStatus = "sconosciuto"
    url: HttpUrl | str | None = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "text")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("field cannot be blank")
        return value.strip()


class DocumentVersion(BaseModel):
    document_key: str
    version_number: int
    text_hash: str
    text: str
    created_at: datetime = Field(default_factory=utc_now)
    source_last_update: datetime | None = None


class LegislativeEvent(BaseModel):
    document_key: str
    event_type: EventType
    summary: str
    created_at: datetime = Field(default_factory=utc_now)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)


class ScoreResult(BaseModel):
    total_score: float
    category_scores: dict[str, float]
    found_terms: dict[str, list[str]]
    relevance_class: RelevanceClass


class TaxonomyClassification(BaseModel):
    domains: list[str]
    matches: dict[str, list[str]]


class RelevanceAssessment(BaseModel):
    document_key: str
    score: float
    relevance_class: RelevanceClass
    category_scores: dict[str, float] = Field(default_factory=dict)
    found_terms: dict[str, list[str]] = Field(default_factory=dict)
    domains: list[str] = Field(default_factory=list)
    method: str = "keyword_rules"
    explanation: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    validated_by_human: bool = False


class Alert(BaseModel):
    document_key: str
    level: AlertLevel
    reason: str
    domains: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction
    generated_at: datetime = Field(default_factory=utc_now)
    status: AlertStatus = "nuovo"


class WeeklyReport(BaseModel):
    period_start: date
    period_end: date
    markdown: str
    generated_at: datetime = Field(default_factory=utc_now)


class ChangeDetectionResult(BaseModel):
    is_new: bool = False
    text_changed: bool = False
    status_changed: bool = False
    metadata_changed: bool = False
    url_changed: bool = False
    events: list[LegislativeEvent] = Field(default_factory=list)
    summary: str = "Nessun cambiamento rilevato."


class LLMClassificationResult(BaseModel):
    relevance_score: float = Field(ge=0, le=1)
    relevance_class: RelevanceClass
    direct_mentions: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    impact_type: list[str] = Field(default_factory=list)
    relevant_passages: list[str] = Field(default_factory=list)
    summary: str
    why_relevant: str
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction
