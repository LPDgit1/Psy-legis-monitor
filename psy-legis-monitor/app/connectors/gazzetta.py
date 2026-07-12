"""Connector for Gazzetta Ufficiale 30-day issue listings."""

from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.parsing import infer_italian_region
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import normalize_text


GAZZETTA_BASE_URL = "https://www.gazzettaufficiale.it"


@dataclass(frozen=True)
class GazzettaSeriesConfig:
    name: str
    list_url: str
    source: str
    level: str
    region: str | None = None
    max_issues: int = 1


def _parse_italian_issue_date(value: str) -> date | None:
    match = re.search(r"(\d{1,2})-(\d{1,2})-(\d{4})", value)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    return date(year, month, day)


def _query_value(url: str, name: str) -> str | None:
    parsed = urlparse(url)
    values = parse_qs(parsed.query)
    found = values.get(name)
    return found[0] if found else None


def _infer_act_type(title: str) -> str:
    folded = title.upper()
    if "DECRETO-LEGGE" in folded or "DECRETO LEGGE" in folded:
        return "decreto_legge"
    if "DECRETO LEGISLATIVO" in folded:
        return "decreto_legislativo"
    if "LEGGE REGIONALE" in folded or folded.startswith("LEGGE "):
        return "legge"
    if "REGOLAMENTO" in folded:
        return "regolamento"
    if "DELIBERA" in folded or "DELIBERAZIONE" in folded:
        return "dgr"
    return "altro"


class GazzettaConnector(BaseConnector):
    """Fetch recently published acts from official Gazzetta issue pages.

    The connector intentionally starts from the official 30-day HTML listings.
    Each issue detail page links individual acts via a stable redaction code
    (`atto.codiceRedazionale`), which is used as the primary identifier.
    """

    name = "gazzetta"

    def __init__(
        self,
        series: list[GazzettaSeriesConfig] | None = None,
        *,
        fetch_act_text: bool = False,
        fetch_method: str = "auto",
        timeout: float = 30,
    ) -> None:
        self.series = series or self.from_config_file()
        self.fetch_act_text = fetch_act_text
        self.fetch_method = fetch_method
        self.timeout = timeout

    @classmethod
    def from_config_file(cls) -> list[GazzettaSeriesConfig]:
        config = load_yaml(settings.sources_path).get("gazzetta", {})
        if not config.get("enabled", True):
            return []
        default_max_issues = int(config.get("max_issues_per_series", 1))
        series_configs = []
        for item in config.get("series", []):
            if item.get("enabled", True):
                series_configs.append(
                    GazzettaSeriesConfig(
                        name=item["name"],
                        list_url=item["list_url"],
                        source=item.get("source", f"Gazzetta Ufficiale - {item['name']}"),
                        level=item.get("level", "nazionale"),
                        region=item.get("region"),
                        max_issues=int(item.get("max_issues", default_max_issues)),
                    )
                )
        return series_configs

    def fetch_documents(self) -> list[LegislativeDocument]:
        documents: list[LegislativeDocument] = []
        for series_config in self.series:
            issue_links = self._fetch_issue_links(series_config)
            for issue_url in issue_links[: series_config.max_issues]:
                documents.extend(self._fetch_issue_documents(series_config, issue_url))
        return documents

    def _fetch_issue_links(
        self,
        series_config: GazzettaSeriesConfig,
    ) -> list[str]:
        html = self._fetch_text(series_config.list_url)
        return parse_issue_links(html, series_config.list_url)

    def _fetch_issue_documents(
        self,
        series_config: GazzettaSeriesConfig,
        issue_url: str,
    ) -> list[LegislativeDocument]:
        documents = parse_issue_documents(
            self._fetch_text(issue_url),
            issue_url,
            series_config=series_config,
            fetched_at=datetime.now(UTC),
        )
        if not self.fetch_act_text:
            return documents

        enriched: list[LegislativeDocument] = []
        for document in documents:
            if not document.url:
                enriched.append(document)
                continue
            try:
                full_text = extract_act_text(self._fetch_text(str(document.url)))
                if full_text:
                    document = document.model_copy(update={"text": full_text})
            except Exception as exc:
                metadata = {**document.metadata, "full_text_error": str(exc)}
                document = document.model_copy(update={"metadata": metadata})
            enriched.append(document)
        return enriched

    def _fetch_text(self, url: str) -> str:
        method = self.fetch_method
        if method == "auto":
            method = "powershell" if sys.platform.startswith("win") else "httpx"
        if method == "powershell":
            return _fetch_text_with_powershell(url, timeout=self.timeout)
        return _fetch_text_with_httpx(url, timeout=self.timeout)


def _fetch_text_with_httpx(url: str, *, timeout: float) -> str:
    headers = {"User-Agent": "psy-legis-monitor/0.1 (+institutional monitoring)"}
    response = httpx.get(url, timeout=timeout, follow_redirects=True, headers=headers)
    response.raise_for_status()
    return response.text


def _fetch_text_with_powershell(url: str, *, timeout: float) -> str:
    escaped_url = url.replace("'", "''")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        f"$url='{escaped_url}'; "
        "$ProgressPreference='SilentlyContinue'; "
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
        "(Invoke-WebRequest -UseBasicParsing -Uri $url).Content",
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return completed.stdout


def parse_issue_links(html: str, base_url: str) -> list[str]:
    """Extract issue detail URLs from a 30-day Gazzetta list page."""

    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        text = normalize_text(anchor.get_text(" "))
        href = anchor["href"]
        if "caricaDettaglio" not in href:
            continue
        if not re.search(r"\bn(?:\.|Â?°|º)?\s*\d+", text, flags=re.IGNORECASE):
            continue
        absolute = urljoin(base_url, href)
        if absolute not in links:
            links.append(absolute)
    return links


def parse_issue_documents(
    html: str,
    issue_url: str,
    *,
    series_config: GazzettaSeriesConfig,
    fetched_at: datetime | None = None,
) -> list[LegislativeDocument]:
    """Extract individual acts from an issue detail page."""

    soup = BeautifulSoup(html, "html.parser")
    issue_title = _issue_title(soup)
    publication_date = _query_value(issue_url, "dataPubblicazioneGazzetta")
    published = date.fromisoformat(publication_date) if publication_date else None
    if published is None:
        published = _parse_italian_issue_date(issue_title)

    grouped: dict[str, list[str]] = defaultdict(list)
    regions_by_url: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "caricaDettaglioAtto" not in href:
            continue
        text = normalize_text(anchor.get_text(" "))
        if text:
            act_url = urljoin(issue_url, href)
            grouped[act_url].append(text)
            region = _region_from_anchor_context(anchor)
            if region and act_url not in regions_by_url:
                regions_by_url[act_url] = region

    documents: list[LegislativeDocument] = []
    for act_url, texts in grouped.items():
        title_part = texts[0]
        summary_part = texts[1] if len(texts) > 1 else None
        identifier = _query_value(act_url, "atto.codiceRedazionale")
        title = title_part if not summary_part else f"{title_part} - {summary_part}"
        document_text = "\n\n".join(
            part for part in [issue_title, title_part, summary_part] if part
        )
        region = (
            series_config.region
            or regions_by_url.get(act_url)
            or infer_italian_region(title, summary_part, document_text, issue_title)
        )
        documents.append(
            LegislativeDocument(
                source=series_config.source,
                source_type="html",
                level=series_config.level,
                region=region,
                act_type=_infer_act_type(title_part),
                identifier=identifier,
                title=title,
                summary=summary_part,
                date_published=published,
                last_update=fetched_at,
                status="pubblicato",
                url=act_url,
                text=document_text,
                metadata={
                    "issue_title": issue_title,
                    "issue_url": issue_url,
                    "series": series_config.name,
                    "accessed_at": (fetched_at or datetime.now(UTC)).isoformat(),
                },
            )
        )
    return documents


def extract_act_text(html: str) -> str:
    """Extract readable text from an individual Gazzetta act page."""

    soup = BeautifulSoup(html, "html.parser")
    for selector in ["script", "style", "nav", "footer"]:
        for node in soup.select(selector):
            node.decompose()
    text = normalize_text(soup.get_text(" "))
    return text


def _issue_title(soup: BeautifulSoup) -> str:
    text = normalize_text(soup.get_text(" "))
    match = re.search(
        r"((?:Serie Generale|3\^?\{?a\}? Serie Speciale - Regioni|3a Serie Speciale - Regioni|3ª Serie Speciale - Regioni|3Âª Serie Speciale - Regioni)"
        r".{0,80}?n\.\s*\d+.{0,40}?\d{4})",
        text,
    )
    if match:
        return normalize_text(match.group(1))
    heading = soup.find(["h1", "h2"])
    if heading:
        return normalize_text(heading.get_text(" "))
    return "Gazzetta Ufficiale"


def _region_from_anchor_context(anchor) -> str | None:
    parts: list[str] = []
    for previous in anchor.find_all_previous(string=True, limit=40):
        text = normalize_text(str(previous))
        if text:
            parts.append(text)
    return infer_italian_region(" ".join(parts))
