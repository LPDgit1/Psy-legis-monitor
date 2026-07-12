"""Connector abstraction for all official and derived sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.schemas import LegislativeDocument


class BaseConnector(ABC):
    """Every connector maps a source-specific payload to LegislativeDocument."""

    name: str

    @abstractmethod
    def fetch_documents(self) -> list[LegislativeDocument]:
        """Fetch and normalize documents from the connector source."""

