"""Generic RSS/Atom connector configured by sources.yml."""

from __future__ import annotations

from datetime import date, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.http_fetch import fetch_text
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import normalize_text


class RSSConnector(BaseConnector):
    name = "rss"

    def __init__(self, source_config: dict | None = None) -> None:
        self.source_config = source_config

    @classmethod
    def from_config_file(cls) -> list["RSSConnector"]:
        config = load_yaml(settings.sources_path)
        connectors = []
        for item in config.get("rss_sources", []):
            if item.get("enabled", False):
                connectors.append(cls(item))
        return connectors

    def fetch_documents(self) -> list[LegislativeDocument]:
        if not self.source_config:
            documents: list[LegislativeDocument] = []
            for connector in self.from_config_file():
                documents.extend(connector.fetch_documents())
            return documents

        payload = fetch_text(
            self.source_config["url"],
            method=self.source_config.get("fetch_method", "auto"),
            timeout=float(self.source_config.get("timeout", 30)),
        )
        root = ElementTree.fromstring(payload)
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        return [self._item_to_document(item) for item in items]

    def _item_to_document(self, item: ElementTree.Element) -> LegislativeDocument:
        def text_at(*names: str) -> str | None:
            for name in names:
                found = item.find(name)
                if found is not None and found.text:
                    return normalize_text(found.text)
                found = item.find(f"{{http://www.w3.org/2005/Atom}}{name}")
                if found is not None and found.text:
                    return normalize_text(found.text)
            return None

        title = text_at("title") or "Documento RSS senza titolo"
        summary = text_at("description", "summary")
        link = text_at("link")
        if not link:
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.attrib.get("href") if atom_link is not None else None
        published_raw = text_at("pubDate", "published", "updated")
        published_date: date | None = None
        if published_raw:
            published_date = _parse_feed_date(published_raw)

        return LegislativeDocument(
            source=self.source_config.get("source", self.source_config.get("name", "RSS")),
            source_type=self.source_config.get("source_type", "rss"),
            level=self.source_config.get("level", "nazionale"),
            region=self.source_config.get("region"),
            act_type=self.source_config.get("act_type", "altro"),
            identifier=text_at("guid", "id") or link,
            title=title,
            summary=summary,
            date_published=published_date,
            status=self.source_config.get("status", "sconosciuto"),
            url=link,
            text="\n\n".join(part for part in [title, summary or ""] if part),
            metadata={"rss_source": self.source_config.get("name")},
        )


def _parse_feed_date(value: str) -> date | None:
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
