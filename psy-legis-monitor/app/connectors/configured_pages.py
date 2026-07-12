"""Reusable wrappers around configured institutional HTML sources."""

from __future__ import annotations

from typing import ClassVar

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.page import PageConnector
from app.core.schemas import LegislativeDocument


class ConfiguredPageGroupConnector(BaseConnector):
    """Base class for connector-specific groups of configured HTML pages."""

    name: ClassVar[str]
    config_key: ClassVar[str]
    default_sources: ClassVar[list[dict]]

    def fetch_documents(self) -> list[LegislativeDocument]:
        section = load_yaml(settings.sources_path).get(self.config_key, {})
        if section and not section.get("enabled", True):
            return []
        source_configs = section.get("sources") if section else None
        if source_configs is None:
            source_configs = self.default_sources

        documents: list[LegislativeDocument] = []
        for item in source_configs:
            if not item.get("enabled", True):
                continue
            documents.extend(PageConnector(item).fetch_documents())
        return documents
