"""Connectors and diagnostics for all official Italian regional bulletins."""

from __future__ import annotations

import hashlib
import io
import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from pypdf import PdfReader

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.http_fetch import fetch_bytes, fetch_text
from app.connectors.page import SourceUnavailableError
from app.connectors.parsing import infer_act_type, parse_connector_date
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import fold_for_search, normalize_text


AdapterType = Literal["html", "html_pdf", "veneto"]

DIRECT_RELEVANCE_TERMS = (
    "psicolog",
    "psicoterap",
    "salute mentale",
    "salute psichica",
    "disagio psicologico",
    "disagio psichico",
    "benessere psicologico",
    "sofferenza psicologica",
    "neuropsic",
    "psicodiagn",
    "consultorio",
    "consultori",
    "dipendenze patologiche",
    "dipendenza da strumenti",
    "dipendenza digitale",
    "disturbi alimentari",
    "disturbo alimentare",
    "disturbi della nutrizione",
    "prevenzione del suicidio",
    "rischio suicidario",
    "autismo",
)

CONTEXT_TERM_GROUPS = (
    ("sanita", "sanitario", "sociosanit", "servizi sociali", "welfare"),
    ("minori", "adolescent", "infanzia", "famiglia", "scuola"),
    ("violenza di genere", "maltrattamento", "vittime", "trauma"),
    ("disabilita", "non autosufficien", "caregiver", "fragilita"),
    ("telemedicina", "salute digitale", "dati sanitari", "consenso informato"),
    ("prevenzione", "presa in carico", "riabilitazione", "assistenza territoriale"),
)

NOISE_TERMS = (
    "veterinar",
    "sanita animale",
    "peste suina",
    "cinghial",
    "suini",
    "influenza aviaria",
    "zooprofilatt",
    "allevament",
    "mangimi",
    "fitosanitari",
    "fitoterap",
    "integratori alimentari",
    "olive da tavola",
    "certificazione per l esportazione",
    "salute digitale dei minori",
    "dipendenza da strumenti e piattaforme digitali",
)

NORMATIVE_MARKERS = (
    "legge",
    "regolamento",
    "decreto",
    "delibera",
    "deliberazione",
    "ordinanza",
    "determinazione",
    "risoluzione",
    "bollettino ufficiale",
)

PDF_ACT_START = re.compile(
    r"(?=(?:LEGGE\s+REGIONALE|REGOLAMENTO\s+REGIONALE|DECRETO(?:\s+DEL)?|"
    r"DELIBERAZIONE(?:\s+DELLA)?|ORDINANZA(?:\s+DEL)?|DETERMINAZIONE(?:\s+DEL)?))",
    flags=re.IGNORECASE,
)


class RegionalBurSource(BaseModel):
    """Validated configuration for one official regional bulletin."""

    model_config = ConfigDict(extra="forbid")

    name: str
    region: str
    url: HttpUrl | str
    enabled: bool = True
    adapter: AdapterType = "html"
    fetch_method: str = "auto"
    timeout: float = 30
    max_items: int = Field(default=12, ge=1, le=100)
    max_detail_links: int = Field(default=2, ge=0, le=5)
    max_pdf_links: int = Field(default=1, ge=0, le=3)
    max_pdf_pages: int = Field(default=12, ge=1, le=50)


class RegionalBurStatus(BaseModel):
    """Per-source health result used by CLI diagnostics and tests."""

    region: str
    source: str
    url: str
    adapter: AdapterType
    status: Literal["ok", "reachable_no_relevant_results", "error"]
    document_count: int = 0
    error: str | None = None


class RegionalBurConnector(BaseConnector):
    """Fetch recent psychology-relevant acts from all configured regional BURs."""

    name = "regional_burs"

    def __init__(self, sources: list[RegionalBurSource] | None = None) -> None:
        self.sources = sources if sources is not None else load_regional_bur_sources()
        self.last_statuses: list[RegionalBurStatus] = []

    def fetch_documents(self) -> list[LegislativeDocument]:
        documents: list[LegislativeDocument] = []
        statuses: list[RegionalBurStatus] = []
        for source in self.sources:
            if not source.enabled:
                continue
            try:
                source_documents = self._fetch_source(source)
                documents.extend(source_documents)
                statuses.append(
                    RegionalBurStatus(
                        region=source.region,
                        source=source.name,
                        url=str(source.url),
                        adapter=source.adapter,
                        status="ok" if source_documents else "reachable_no_relevant_results",
                        document_count=len(source_documents),
                    )
                )
            except Exception as exc:
                statuses.append(
                    RegionalBurStatus(
                        region=source.region,
                        source=source.name,
                        url=str(source.url),
                        adapter=source.adapter,
                        status="error",
                        error=" ".join(str(exc).split())[:350],
                    )
                )
        self.last_statuses = statuses
        if statuses and all(status.status == "error" for status in statuses):
            raise RuntimeError("Nessuno dei BUR regionali configurati e raggiungibile")
        return _deduplicate_documents(documents)

    def probe_sources(self) -> list[RegionalBurStatus]:
        self.fetch_documents()
        return self.last_statuses

    def _fetch_source(self, source: RegionalBurSource) -> list[LegislativeDocument]:
        if source.adapter == "veneto":
            from app.connectors.regions.veneto import VenetoConnector

            return VenetoConnector(
                url=str(source.url),
                fetch_method=source.fetch_method,
                timeout=source.timeout,
            ).fetch_documents()

        fetched_at = datetime.now(UTC)
        page_url = str(source.url)
        html = fetch_text(page_url, method=source.fetch_method, timeout=source.timeout)
        _raise_if_blocked(html, page_url)
        pages = [(page_url, html)]
        for detail_url in find_recent_detail_links(html, page_url)[: source.max_detail_links]:
            try:
                detail_html = fetch_text(
                    detail_url,
                    method=source.fetch_method,
                    timeout=source.timeout,
                )
                _raise_if_blocked(detail_html, detail_url)
                pages.append((detail_url, detail_html))
            except Exception:
                continue

        documents: list[LegislativeDocument] = []
        pdf_urls: list[str] = []
        for current_url, current_html in pages:
            documents.extend(
                parse_regional_bur_html(
                    current_html,
                    current_url,
                    source=source,
                    fetched_at=fetched_at,
                )
            )
            if source.adapter == "html_pdf":
                pdf_urls.extend(find_recent_pdf_links(current_html, current_url))

        for pdf_url in list(dict.fromkeys(pdf_urls))[: source.max_pdf_links]:
            try:
                pdf_data = fetch_bytes(
                    pdf_url,
                    method=source.fetch_method,
                    timeout=source.timeout,
                    max_bytes=15_000_000,
                )
                documents.extend(
                    parse_regional_bur_pdf(
                        pdf_data,
                        pdf_url,
                        source=source,
                        fetched_at=fetched_at,
                    )
                )
            except Exception:
                continue
        return documents


def load_regional_bur_sources() -> list[RegionalBurSource]:
    section = load_yaml(settings.sources_path).get("regional_burs", {})
    if section and not section.get("enabled", True):
        return []
    return [
        RegionalBurSource.model_validate(item)
        for item in section.get("sources", [])
        if item.get("enabled", True)
    ]


def parse_regional_bur_html(
    html: str,
    page_url: str,
    *,
    source: RegionalBurSource,
    fetched_at: datetime,
) -> list[LegislativeDocument]:
    """Extract linked acts whose visible title or nearby context is relevant."""

    soup = BeautifulSoup(html, "html.parser")
    documents: list[LegislativeDocument] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute_url = urljoin(page_url, str(anchor["href"]))
        title = normalize_text(anchor.get_text(" "))
        context = _nearby_context(anchor)
        candidate = normalize_text(" ".join(part for part in [title, context] if part))
        if not candidate or not is_relevant_regional_act(candidate):
            continue
        if not _has_normative_marker(candidate, absolute_url):
            continue
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        display_title = _best_candidate_title(title, context)
        documents.append(
            _build_document(
                display_title,
                absolute_url,
                source=source,
                fetched_at=fetched_at,
                text=candidate,
                origin="html_index",
            )
        )
        if len(documents) >= source.max_items:
            break
    return documents


def find_recent_pdf_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute_url = urljoin(page_url, str(anchor["href"]))
        anchor_text = fold_for_search(anchor.get_text(" "))
        folded = fold_for_search(f"{anchor.get_text(' ')} {absolute_url}")
        parsed_path = urlparse(absolute_url).path.lower()
        if not (
            parsed_path.endswith(".pdf")
            or "scarica pdf" in folded
            or anchor_text == "scarica"
            or "download" in folded
        ):
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        links.append(absolute_url)
    return links


def find_recent_detail_links(html: str, page_url: str) -> list[str]:
    """Find a bounded set of recent issue/detail pages below a BUR index."""

    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    seen: set[str] = {page_url}
    for anchor in soup.find_all("a", href=True):
        absolute_url = urljoin(page_url, str(anchor["href"]))
        parsed_path = urlparse(absolute_url).path.lower()
        if parsed_path.endswith((".pdf", ".p7m")):
            continue
        folded = fold_for_search(f"{anchor.get_text(' ')} {absolute_url}")
        is_issue_link = any(
            marker in folded
            for marker in (
                "bollettino",
                "ordinario n",
                "speciale n",
                "supplemento n",
                "visualizza bur",
                "numero corrente",
                "bur n ",
                "burl n ",
                "burp n ",
                "burm integral",
            )
        )
        if not is_issue_link or absolute_url in seen:
            continue
        seen.add(absolute_url)
        links.append(absolute_url)
    return links


def parse_regional_bur_pdf(
    data: bytes,
    pdf_url: str,
    *,
    source: RegionalBurSource,
    fetched_at: datetime,
) -> list[LegislativeDocument]:
    reader = PdfReader(io.BytesIO(data))
    page_text = "\n".join(
        page.extract_text() or "" for page in reader.pages[: source.max_pdf_pages]
    )
    normalized = normalize_text(page_text)
    if not normalized:
        return []

    chunks = [normalize_text(chunk) for chunk in PDF_ACT_START.split(normalized)]
    documents: list[LegislativeDocument] = []
    for chunk in chunks:
        if not chunk or not is_relevant_regional_act(chunk):
            continue
        if not _has_normative_marker(chunk, pdf_url):
            continue
        title = _pdf_chunk_title(chunk)
        documents.append(
            _build_document(
                title,
                pdf_url,
                source=source,
                fetched_at=fetched_at,
                text=chunk[:5000],
                origin="bur_pdf",
            )
        )
        if len(documents) >= source.max_items:
            break
    return documents


def is_relevant_regional_act(value: str) -> bool:
    folded = fold_for_search(value)
    has_direct = any(term in folded for term in DIRECT_RELEVANCE_TERMS)
    if any(term in folded for term in NOISE_TERMS) and not has_direct:
        return False
    if has_direct:
        return True
    matched_groups = sum(any(term in folded for term in group) for group in CONTEXT_TERM_GROUPS)
    return matched_groups >= 2


def _build_document(
    title: str,
    url: str,
    *,
    source: RegionalBurSource,
    fetched_at: datetime,
    text: str,
    origin: str,
) -> LegislativeDocument:
    normalized_title = normalize_text(title)[:700]
    normalized_text = normalize_text(text)
    digest = hashlib.sha256(f"{source.region}|{url}|{normalized_title}".encode("utf-8")).hexdigest()[:20]
    return LegislativeDocument(
        source=source.name,
        source_type="pdf" if origin == "bur_pdf" else "html",
        level="regionale",
        region=source.region,
        act_type=infer_act_type(f"{normalized_title} {normalized_text}", default="altro"),
        identifier=f"BUR-{source.region}-{digest}",
        title=normalized_title,
        summary=None,
        date_published=parse_connector_date(normalized_title) or parse_connector_date(normalized_text[:600]),
        last_update=fetched_at,
        status="pubblicato",
        url=url,
        text=normalized_text,
        metadata={
            "connector": RegionalBurConnector.name,
            "adapter": source.adapter,
            "origin": origin,
            "container_url": str(source.url),
            "accessed_at": fetched_at.isoformat(),
        },
    )


def _nearby_context(anchor) -> str:
    for parent in anchor.parents:
        if getattr(parent, "name", None) not in {"li", "article", "section", "tr", "div"}:
            continue
        text = normalize_text(parent.get_text(" "))
        if 20 <= len(text) <= 1600:
            return text
    return ""


def _best_candidate_title(anchor_text: str, context: str) -> str:
    title = normalize_text(anchor_text)
    if len(title) >= 25 and fold_for_search(title) not in {"leggi", "dettaglio", "scarica pdf"}:
        return title
    context = normalize_text(context)
    return context[:700] or title or "Atto pubblicato nel Bollettino Ufficiale regionale"


def _pdf_chunk_title(chunk: str) -> str:
    normalized = normalize_text(chunk)
    match = re.search(r"\b(?:OGGETTO|Oggetto)\s*[:.-]\s*(.{20,600}?)(?=\s{2,}|$)", normalized)
    if match:
        return normalize_text(match.group(1))[:700]
    sentence = re.split(r"(?<=[.;])\s+", normalized, maxsplit=1)[0]
    return sentence[:700]


def _has_normative_marker(text: str, url: str) -> bool:
    folded = fold_for_search(text)
    return any(marker in folded for marker in NORMATIVE_MARKERS) or urlparse(url).path.lower().endswith(".pdf")


def _raise_if_blocked(html: str, page_url: str) -> None:
    folded = fold_for_search(html[:8000])
    if "checking your browser before accessing" in folded or "cf-chl-" in html:
        raise SourceUnavailableError(f"{page_url} ha restituito un browser-check")
    if not BeautifulSoup(html, "html.parser").find(["html", "body", "a"]):
        raise SourceUnavailableError(f"{page_url} non ha restituito HTML utilizzabile")


def _deduplicate_documents(documents: list[LegislativeDocument]) -> list[LegislativeDocument]:
    result: list[LegislativeDocument] = []
    seen: set[str] = set()
    for document in documents:
        key = str(document.identifier or document.url or document.title)
        if key in seen:
            continue
        seen.add(key)
        result.append(document)
    return result
