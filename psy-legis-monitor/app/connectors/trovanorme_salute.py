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
from app.core.text_cleaning import fold_for_search, normalize_text


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

MINISTRY_DIRECT_RELEVANCE_TERMS = [
    "psicolog",
    "psicoterapia",
    "psicoterapeut",
    "counsel",
    "salute mentale",
    "bonus psicologo",
    "consultori",
    "neuropsichiatria",
    "neuropsic",
    "dipendenze",
    "disturbi alimentari",
    "disturbo alimentare",
    "disturbi della nutrizione",
    "suicidio",
    "disagio psicologico",
    "disagio psichico",
    "autismo",
]

MINISTRY_LOW_SIGNAL_TERMS = [
    "telemedicina",
    "fascicolo sanitario",
    "dati sanitari",
    "consenso informato",
    "violenza di genere",
]

MINISTRY_EXCLUSION_TERMS = [
    "fitoterap",
    "medicinale omeopatico",
    "medicinali omeopatici",
    "prodotto omeopatico",
    "prodotti omeopatici",
    "prodotto erboristico",
    "prodotti erboristici",
    "integratori alimentari",
    "veterinar",
    "animale",
    "animali",
    "sanita animale",
    "farmaco veterinario",
    "farmaci veterinari",
    "medicinale veterinario",
    "medicinali veterinari",
    "mangimi",
    "allevament",
    "acquacoltura",
    "peste suina",
    "peste suina africana",
    "cinghial",
    "suini",
    "fauna selvatica",
    "animali selvatici",
    "attivita venatoria",
    "prelievo venatorio",
    "caccia",
    "abbattimento selettivo",
    "carni di selvaggina",
    "influenza aviaria",
    "blue tongue",
    "lingua blu",
    "zooprofilatt",
    "epizoo",
    "biosicurezza",
    "zootecnic",
    "prodotti fitosanitari",
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
            if not is_ministry_health_document_relevant(document.title, document.text):
                continue
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
                if not is_ministry_health_document_relevant(title, title, search_term=term):
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
        title = _enrich_act_title(title, _nearby_act_context(anchor))
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
    act_label = _act_label_from_enriched_title(normalized_title)
    summary_parts = [
        f"Atto: {act_label}" if act_label else None,
        f"Risultato Trova Norme Salute per: {search_term}",
    ]
    summary = ". ".join(part for part in summary_parts if part)
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


def is_ministry_health_document_relevant(
    title: str,
    text: str | None = None,
    *,
    search_term: str | None = None,
) -> bool:
    folded = fold_for_search(" ".join(part for part in [title, text, search_term] if part))
    title_text = fold_for_search(" ".join(part for part in [title, text] if part))
    has_direct_relevance = any(term in title_text for term in MINISTRY_DIRECT_RELEVANCE_TERMS)
    has_low_signal_relevance = any(term in title_text for term in MINISTRY_LOW_SIGNAL_TERMS)
    came_from_direct_search = bool(search_term and fold_for_search(search_term) in MINISTRY_DIRECT_RELEVANCE_TERMS)
    has_exclusion = any(term in folded for term in MINISTRY_EXCLUSION_TERMS)
    if has_exclusion and not has_direct_relevance:
        return False
    return has_direct_relevance or has_low_signal_relevance or came_from_direct_search


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


def _nearby_act_context(anchor) -> str:
    for parent in anchor.parents:
        if getattr(parent, "name", None) not in {"li", "article", "section", "div", "tr"}:
            continue
        text = normalize_text(parent.get_text(" "))
        if text and len(text) <= 900:
            return text
    return ""


def _enrich_act_title(title: str, context: str) -> str:
    subject = _extract_act_subject(title, context)
    if not subject:
        return title
    return f"{subject} ({title})"


def _extract_act_subject(title: str, context: str) -> str | None:
    text = normalize_text(context)
    if not text:
        return None

    labeled = re.search(
        r"\b(?:oggetto|titolo|descrizione|argomento|materia)\s*[:\-]\s*(?P<subject>.+)",
        text,
        flags=re.IGNORECASE,
    )
    candidate = labeled.group("subject") if labeled else text
    candidate = re.sub(re.escape(title), " ", candidate, flags=re.IGNORECASE)
    candidate = re.sub(
        r"\b(?:leggi tutto|visualizza|dettaglio atto|dettaglio|scarica|pdf|html)\b",
        " ",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r"\b(?:tipo atto|data pubblicazione|data|numero|atto)\s*[:\-]\s*", " ", candidate, flags=re.IGNORECASE)
    candidate = normalize_text(candidate).strip(" -:;,.")

    if not _is_informative_subject(candidate, title):
        return None
    return _shorten_subject(candidate)


def _is_informative_subject(candidate: str, title: str) -> bool:
    folded_candidate = fold_for_search(candidate)
    folded_title = fold_for_search(title)
    if not folded_candidate or folded_candidate == folded_title:
        return False
    if len(candidate) < 18:
        return False
    if folded_candidate in {"leggi tutto", "dettaglio", "dettaglio atto"}:
        return False
    return any(char.isalpha() for char in candidate)


def _shorten_subject(value: str, *, max_length: int = 180) -> str:
    text = normalize_text(value)
    if len(text) <= max_length:
        return text
    truncated = text[: max_length + 1].rsplit(" ", 1)[0].rstrip(" -:;,.")
    return f"{truncated}..."


def _act_label_from_enriched_title(title: str) -> str | None:
    match = re.search(r"\((?P<label>[^()]*\d{1,2}[/-]\d{1,2}[/-]\d{4}[^()]*)\)$", title)
    if not match:
        return None
    return normalize_text(match.group("label"))
