"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[str] = mapped_column(String(64), index=True)
    region: Mapped[str | None] = mapped_column(String(128), index=True)
    act_type: Mapped[str] = mapped_column(String(128), index=True)
    identifier: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    date_presented: Mapped[date | None] = mapped_column(Date)
    date_published: Mapped[date | None] = mapped_column(Date, index=True)
    last_update: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(128), index=True)
    url: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    events: Mapped[list["LegislativeEvent"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    assessments: Mapped[list["RelevanceAssessment"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_last_update: Mapped[datetime | None] = mapped_column(DateTime)

    document: Mapped[Document] = relationship(back_populates="versions")


class LegislativeEvent(Base):
    __tablename__ = "legislative_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    summary: Mapped[str] = mapped_column(Text)
    before_json: Mapped[dict] = mapped_column("before", JSON, default=dict)
    after_json: Mapped[dict] = mapped_column("after", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped[Document] = relationship(back_populates="events")


class RelevanceAssessment(Base):
    __tablename__ = "relevance_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    relevance_class: Mapped[str] = mapped_column(String(64), index=True)
    category_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    found_terms: Mapped[dict] = mapped_column(JSON, default=dict)
    domains: Mapped[list] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(128), default="keyword_rules")
    explanation: Mapped[str | None] = mapped_column(Text)
    validated_by_human: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped[Document] = relationship(back_populates="assessments")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    level: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(Text)
    domains: Mapped[list] = mapped_column(JSON, default=list)
    recommended_action: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), default="nuovo", index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped[Document] = relationship(back_populates="alerts")


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    markdown: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

