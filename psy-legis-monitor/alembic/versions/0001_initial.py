"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_key", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=64), nullable=False),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("act_type", sa.String(length=128), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("date_presented", sa.Date(), nullable=True),
        sa.Column("date_published", sa.Date(), nullable=True),
        sa.Column("last_update", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_documents_document_key", "documents", ["document_key"], unique=True)
    op.create_index("ix_documents_source", "documents", ["source"])
    op.create_index("ix_documents_source_type", "documents", ["source_type"])
    op.create_index("ix_documents_level", "documents", ["level"])
    op.create_index("ix_documents_region", "documents", ["region"])
    op.create_index("ix_documents_act_type", "documents", ["act_type"])
    op.create_index("ix_documents_identifier", "documents", ["identifier"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_date_published", "documents", ["date_published"])
    op.create_index("ix_documents_text_hash", "documents", ["text_hash"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("source_last_update", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_index("ix_document_versions_text_hash", "document_versions", ["text_hash"])

    op.create_table(
        "legislative_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_legislative_events_document_id", "legislative_events", ["document_id"])
    op.create_index("ix_legislative_events_event_type", "legislative_events", ["event_type"])

    op.create_table(
        "relevance_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("relevance_class", sa.String(length=64), nullable=False),
        sa.Column("category_scores", sa.JSON(), nullable=False),
        sa.Column("found_terms", sa.JSON(), nullable=False),
        sa.Column("domains", sa.JSON(), nullable=False),
        sa.Column("method", sa.String(length=128), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("validated_by_human", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_relevance_assessments_document_id", "relevance_assessments", ["document_id"]
    )
    op.create_index(
        "ix_relevance_assessments_relevance_class",
        "relevance_assessments",
        ["relevance_class"],
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("domains", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_alerts_document_id", "alerts", ["document_id"])
    op.create_index("ix_alerts_level", "alerts", ["level"])
    op.create_index("ix_alerts_status", "alerts", ["status"])

    op.create_table(
        "weekly_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("weekly_reports")
    op.drop_table("alerts")
    op.drop_table("relevance_assessments")
    op.drop_table("legislative_events")
    op.drop_table("document_versions")
    op.drop_table("documents")

