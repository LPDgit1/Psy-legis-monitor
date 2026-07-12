"""Connector for the official Trova Norme Salute portal."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.connectors.base import BaseConnector
from app.connectors.http_fetch import fetch_text
from app.connectors.parsing import infer_act_type, infer_status, parse_connector_date
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import normalize_text


TROVANORME_HOME_URL = "https://www.trovanorme.salute.gov.it/norme/ricerca"
TROVANORME_SEARCH_URL = "https://www.trovanorme.salute.gov.it/norme/ricercaAtti?word={term}"
DEFAULT_SEARCH_TERMS = [
    "psicologo",
    "psicoterapia",
    "salute mentale",
    "consultori",
    "neuropsichiatria",
    "dipendenze",
    "disagio psicologico",
    "bonus psicologo",
]


class TrovaNormeSaluteConnector(BaseConnector):
    """Fetch recent health-law items from the official Ministry/IPZS portal."""

    name = "trovanorme_salute"

    def __init__(
        self,
        *,
        url: str = TROVANORME_HOME_URL,
        fetch_method: str = "auto",
        timeout: float = 30,
        max_items: int = 10,
        search_terms: list[str] | None = None,
        max_items_per_search: int = 3,
    ) -> None:
        self.url = url
        self.fetch_method = fetch_method
        self.timeout = timeout
        self.max_items = max_items
        self.search_terms = search_terms or DEFAULT_SEARCH_TERMS
        self.max_items_per_search = max_items_per_search

    def fetch_documents(self) -> list[LegislativeDocument]:
        fetched_at = datetime.now(UTC)
        html = fetch_text(self.url, method=self.fetch_method, timeout=self.timeout)
        items = parse_trovanorme_news_links(html, self.url, max_items=self.max_items)

        documents: list[LegislativeDocument] = []
        seen_urls: set[str] = set()
        for title, detail_url in items:
            detail_html = fetch_text(detail_url, method=self.fetch_method, timeout=self.timeout)
            document = (
                parse_trovanorme_detail(
                    detail_html,
                    detail_url,
                    fallback_title=title,
                    fetched_at=fetched_at,
                )
            )
            documents.append(document)
            seen_urls.add(document.url)

        for term in self.search_terms:
            search_url = TROVANORME_SEARCH_URL.format(term=term.replace(" ", "+"))
            search_html = fetch_text(search_url, method=self.fetch_method, timeout=self.timeout)
            for title, detail_url in parse_trovanorme_act_links(
                search_html,
                search_url,
                max_items=self.max_items_per_search,
            ):
                if detail_url in seen_urls:
                    continue
                seen_urls.add(detail_url)
                documents.append(
                    build_trovanorme_act_document(
                        title,
                        detail_url,
                        search_term=term,
                        fetched_at=fetched_at,
                    )
                )
        return documents


def parse_trovanorme_news_links(
    html: str,
    page_url: str,
    *,
    max_items: int,
) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if "dettaglioNews" not in href:
            continue
        absolute_url = urljoin(page_url, href)
        if absolute_url in seen:
            continue
        title = normalize_text(anchor.get_text(" "))
        if not title:
            continue
        seen.add(absolute_url)
        links.append((title, absolute_url))
        if len(links) >= max_items:
            break
    return links


def parse_trovanorme_act_links(
    html: str,
    page_url: str,
    *,
    max_items: int,
) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if "dettaglioAtto" not in href:
            continue
        title = normalize_text(anchor.get_text(" "))
        if not title or title.lower() == "leggi tutto":
            continue
        absolute_url = urljoin(page_url, href)
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        links.append((title, absolute_url))
        if len(links) >= max_items:
            break
    return links


def build_trovanorme_act_document(
    title: str,
    page_url: str,
    *,
    search_term: str,
    fetched_at: datetime,
) -> LegislativeDocument:
    normalized_title = normalize_text(title)
    summary = f"Risultato Trova Norme Salute per: {search_term}"
    act_text = f"{normalized_title} {summary}"
    return LegislativeDocument(
        source="Ministero della Salute - Trova Norme Salute",
        source_type="html",
        level="nazionale",
        act_type=infer_act_type(act_text, default="altro"),
        identifier=page_url,
        title=normalized_title,
        summary=summary,
        date_published=parse_connector_date(normalized_title),
        last_update=fetched_at,
        status="pubblicato",
        url=page_url,
        text=act_text,
        metadata={
            "connector": TrovaNormeSaluteConnector.name,
            "search_term": search_term,
            "accessed_at": fetched_at.isoformat(),
        },
    )


def parse_trovanorme_detail(
    html: str,
    page_url: str,
    *,
    fallback_title: str,
    fetched_at: datetime,
) -> LegislativeDocument:
    soup = BeautifulSoup(html, "html.parser")
    heading = _find_news_heading(soup)
    raw_title = normalize_text(heading.get_text(" ")) if heading else fallback_title
    date_published = parse_connector_date(raw_title)
    title = _strip_heading_date(raw_title) or fallback_title
    summary = _extract_news_summary(soup, heading)
    act_text = " ".join(part for part in [title, summary] if part)

    return LegislativeDocument(
        source="Ministero della Salute - Trova Norme Salute",
        source_type="html",
        level="nazionale",
        act_type=infer_act_type(act_text, default="altro"),
        identifier=page_url,
        title=title,
        summary=summary,
        date_published=date_published,
        last_update=fetched_at,
        status=infer_status(act_text, default="pubblicato"),
        url=page_url,
        text=act_text,
        metadata={
            "connector": TrovaNormeSaluteConnector.name,
            "page_source": TROVANORME_HOME_URL,
            "accessed_at": fetched_at.isoformat(),
        },
    )


def _find_news_heading(soup: BeautifulSoup):
    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = normalize_text(heading.get_text(" "))
        if re.search(r"\b\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4}\s+-", text):
            return heading
    return None


def _strip_heading_date(value: str) -> str:
    return normalize_text(
        re.sub(r"^\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4}\s+-\s*", "", value)
    )


def _extract_news_summary(soup: BeautifulSoup, heading) -> str | None:
    if heading is None:
        return None
    parts: list[str] = []
    for sibling in heading.find_next_siblings():
        if getattr(sibling, "name", None) in {"h1", "h2", "h3", "h4", "footer"}:
            break
        text = normalize_text(sibling.get_text(" "))
        if text:
            parts.append(text)
    summary = normalize_text(" ".join(parts))
    return summary or None
