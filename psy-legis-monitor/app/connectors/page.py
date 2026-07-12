"""Configurable connector for public institutional pages."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.http_fetch import fetch_text
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import fold_for_search, normalize_text


GENERIC_LINK_TEXTS = {
    "scopri tutto",
    "leggi di piu",
    "continua",
    "read more",
}


class SourceUnavailableError(RuntimeError):
    """Raised when a public source returns a technical block page."""


class PageConnector(BaseConnector):
    """Extract linked public notices from configured institutional HTML pages."""

    name = "page"

    def __init__(self, source_config: dict | None = None) -> None:
        self.source_config = source_config

    @classmethod
    def from_config_file(cls) -> list["PageConnector"]:
        config = load_yaml(settings.sources_path)
        connectors = []
        for item in config.get("page_sources", []):
            if item.get("enabled", False):
                connectors.append(cls(item))
        return connectors

    def fetch_documents(self) -> list[LegislativeDocument]:
        if not self.source_config:
            documents: list[LegislativeDocument] = []
            for connector in self.from_config_file():
                documents.extend(connector.fetch_documents())
            return documents

        html = fetch_text(
            self.source_config["url"],
            method=self.source_config.get("fetch_method", "auto"),
            timeout=float(self.source_config.get("timeout", 30)),
        )
        return parse_page_documents(
            html,
            self.source_config["url"],
            source_config=self.source_config,
            fetched_at=datetime.now(UTC),
        )


def parse_page_documents(
    html: str,
    page_url: str,
    *,
    source_config: dict,
    fetched_at: datetime | None = None,
) -> list[LegislativeDocument]:
    soup = BeautifulSoup(html, "html.parser")
    _raise_if_technical_block_page(soup, html, page_url)
    include_patterns = [_compile_pattern(pattern) for pattern in source_config.get("include_patterns", [])]
    exclude_patterns = [_compile_pattern(pattern) for pattern in source_config.get("exclude_patterns", [])]
    max_items = int(source_config.get("max_items", 50))

    documents: list[LegislativeDocument] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute_url = urljoin(page_url, anchor["href"])
        slug_title = _title_from_url(absolute_url)
        if _is_generic_anchor(anchor) and _matches_any(slug_title, include_patterns):
            title = slug_title
        else:
            title = _anchor_title(anchor)
        if not title:
            continue
        candidate = f"{title} {absolute_url}"
        if include_patterns and not any(pattern.search(candidate) for pattern in include_patterns):
            continue
        if include_patterns and not any(pattern.search(title) for pattern in include_patterns):
            if slug_title and any(pattern.search(slug_title) for pattern in include_patterns):
                title = slug_title
        candidate = f"{title} {absolute_url}"
        if exclude_patterns and any(
            pattern.search(title) or pattern.search(candidate) for pattern in exclude_patterns
        ):
            continue
        if absolute_url in seen_urls:
            continue

        seen_urls.add(absolute_url)
        documents.append(
            LegislativeDocument(
                source=source_config.get("source", source_config.get("name", "Pagina istituzionale")),
                source_type=source_config.get("source_type", "html"),
                level=source_config.get("level", "nazionale"),
                region=source_config.get("region"),
                act_type=source_config.get("act_type", "altro"),
                identifier=absolute_url,
                title=title,
                summary=None,
                date_published=None,
                last_update=fetched_at,
                status=source_config.get("status", "pubblicato"),
                url=absolute_url,
                text=title,
                metadata={
                    "page_source": source_config.get("name"),
                    "container_url": page_url,
                    "accessed_at": (fetched_at or datetime.now(UTC)).isoformat(),
                },
            )
        )
        if len(documents) >= max_items:
            break
    return documents


def _anchor_title(anchor) -> str:
    text = normalize_text(anchor.get_text(" "))
    if text and fold_for_search(text) not in GENERIC_LINK_TEXTS:
        return text

    heading = _nearby_heading(anchor)
    if heading:
        return heading
    return text


def _nearby_heading(anchor) -> str:
    for sibling in anchor.find_previous_siblings(["h1", "h2", "h3", "h4", "h5"]):
        title = normalize_text(sibling.get_text(" "))
        if title:
            return title
    for parent in anchor.parents:
        heading = parent.find(["h1", "h2", "h3", "h4", "h5"])
        if heading:
            title = normalize_text(heading.get_text(" "))
            if title:
                return title
        previous = parent.find_previous(["h1", "h2", "h3", "h4", "h5"])
        if previous:
            title = normalize_text(previous.get_text(" "))
            if title:
                return title
    return ""


def _compile_pattern(pattern: str) -> re.Pattern:
    return re.compile(pattern, flags=re.IGNORECASE)


def _is_generic_anchor(anchor) -> bool:
    text = fold_for_search(anchor.get_text(" "))
    return not text or text in GENERIC_LINK_TEXTS


def _matches_any(value: str, patterns: list[re.Pattern]) -> bool:
    return bool(value) and any(pattern.search(value) for pattern in patterns)


def _raise_if_technical_block_page(soup: BeautifulSoup, html: str, page_url: str) -> None:
    title = normalize_text(soup.title.get_text(" ")) if soup.title else ""
    folded_title = fold_for_search(title)
    if folded_title == "gcore" or "/sbbi/?sbbpg=sbbShell" in html or "sbbgscc" in html:
        raise SourceUnavailableError(
            f"{page_url} ha restituito una pagina tecnica Gcore/anti-bot invece dei contenuti pubblici"
        )


def _title_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if not path:
        return ""
    slug = unquote(path.rsplit("/", 1)[-1])
    title = normalize_text(re.sub(r"[-_]+", " ", slug))
    return title[:1].upper() + title[1:] if title else ""
