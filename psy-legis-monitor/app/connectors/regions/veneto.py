"""Connector for Regione Veneto BUR latest issues."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.configured_pages import ConfiguredPageGroupConnector
from app.connectors.http_fetch import fetch_text
from app.connectors.parsing import parse_connector_date
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import normalize_text


VENETO_BUR_URL = "https://bur.regione.veneto.it/"


class VenetoConnector(BaseConnector):
    """Fetch latest official Veneto BUR issue references."""

    name = "regione_veneto"

    def __init__(
        self,
        *,
        url: str | None = None,
        fetch_method: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        config = load_yaml(settings.sources_path).get("regione_veneto", {})
        self.enabled = config.get("enabled", True) if enabled is None else enabled
        self.url = url or config.get("url", VENETO_BUR_URL)
        self.fetch_method = fetch_method or config.get("fetch_method", "auto")
        self.timeout = float(timeout if timeout is not None else config.get("timeout", 30))

    def fetch_documents(self) -> list[LegislativeDocument]:
        if not self.enabled:
            return []
        fetched_at = datetime.now(UTC)
        documents: list[LegislativeDocument] = []
        errors: list[Exception] = []
        try:
            html = fetch_text(self.url, method=self.fetch_method, timeout=self.timeout)
            documents.extend(parse_veneto_bur_latest(html, self.url, fetched_at=fetched_at))
        except Exception as exc:
            errors.append(exc)
        try:
            documents.extend(_VenetoConfiguredPages().fetch_documents())
        except Exception as exc:
            errors.append(exc)
        if not documents and errors:
            raise RuntimeError(
                "Regione Veneto non interrogabile: BUR e pagina normativa non disponibili"
            ) from errors[0]
        return documents


def parse_veneto_bur_latest(
    html: str,
    page_url: str,
    *,
    fetched_at: datetime,
) -> list[LegislativeDocument]:
    text = normalize_text(html)
    documents: list[LegislativeDocument] = []
    seen: set[str] = set()
    for match in re.finditer(r"\bBUR\s+N\.\s*(\d+)\s+del\s+(\d{1,2}/\d{1,2}/\d{4})", text, flags=re.I):
        number, raw_date = match.groups()
        identifier = f"BUR Veneto n. {number}/{raw_date[-4:]}"
        if identifier in seen:
            continue
        seen.add(identifier)
        title = f"BUR Veneto n. {number} del {raw_date}"
        documents.append(
            LegislativeDocument(
                source="Regione Veneto - Bollettino Ufficiale",
                source_type="html",
                level="regionale",
                region="Veneto",
                act_type="bur",
                identifier=identifier,
                title=title,
                date_published=parse_connector_date(raw_date),
                last_update=fetched_at,
                status="pubblicato",
                url=page_url,
                text=title,
                metadata={
                    "connector": VenetoConnector.name,
                    "page_source": page_url,
                    "kind": "latest_bur_issue",
                    "accessed_at": fetched_at.isoformat(),
                },
            )
        )
    return documents


class _VenetoConfiguredPages(ConfiguredPageGroupConnector):
    name = "regione_veneto_pages"
    config_key = "regione_veneto_pages"
    default_sources = [
        {
            "name": "Regione Veneto - Normativa",
            "enabled": True,
            "source": "Regione Veneto - Normativa",
            "level": "regionale",
            "region": "Veneto",
            "act_type": "altro",
            "status": "pubblicato",
            "url": "https://www.regione.veneto.it/web/guest/normativa",
            "source_type": "html",
            "fetch_method": "auto",
            "max_items": 20,
            "include_patterns": [
                "legge regionale",
                "deliberazione",
                "sanita",
                "sociale",
                "salute mentale",
                "consultori",
                "psicolog",
            ],
            "exclude_patterns": ["Cookie", "Privacy"],
        }
    ]
