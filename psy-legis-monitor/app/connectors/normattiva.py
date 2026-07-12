"""Connector for Normattiva updates and approved-not-yet-published laws."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.http_fetch import fetch_text
from app.connectors.parsing import ITALIAN_MONTHS, infer_act_type, parse_connector_date
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import fold_for_search, normalize_text


NORMATTIVA_HOME_URL = "https://www.normattiva.it/"
APPROVED_NOT_PUBLISHED_URL = "https://www.parlamento.it/leg/ldl_new/v3/sldlelencoddlappnonpub.htm"


class NormattivaConnector(BaseConnector):
    """Fetch recent consolidated-law updates and final approvals pending publication."""

    name = "normattiva"

    def __init__(
        self,
        *,
        homepage_url: str | None = None,
        approved_not_published_url: str | None = None,
        fetch_method: str | None = None,
        timeout: float | None = None,
        max_items: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        config = load_yaml(settings.sources_path).get("normattiva", {})
        self.enabled = config.get("enabled", True) if enabled is None else enabled
        self.homepage_url = homepage_url or config.get("homepage_url", NORMATTIVA_HOME_URL)
        self.approved_not_published_url = (
            approved_not_published_url
            or config.get("approved_not_published_url", APPROVED_NOT_PUBLISHED_URL)
        )
        self.fetch_method = fetch_method or config.get("fetch_method", "auto")
        self.timeout = float(timeout if timeout is not None else config.get("timeout", 30))
        self.max_items = _bounded_limit(max_items if max_items is not None else config.get("max_items", 30))

    def fetch_documents(self) -> list[LegislativeDocument]:
        if not self.enabled:
            return []
        fetched_at = datetime.now(UTC)
        documents: list[LegislativeDocument] = []
        home_html = fetch_text(self.homepage_url, method=self.fetch_method, timeout=self.timeout)
        documents.extend(
            parse_normattiva_home_updates(
                home_html,
                self.homepage_url,
                fetched_at=fetched_at,
                max_items=self.max_items,
            )
        )
        approved_html = fetch_text(
            self.approved_not_published_url,
            method=self.fetch_method,
            timeout=self.timeout,
        )
        documents.extend(
            parse_approved_not_published_laws(
                approved_html,
                self.approved_not_published_url,
                fetched_at=fetched_at,
                max_items=self.max_items,
            )
        )
        return documents[: self.max_items * 2]


def parse_normattiva_home_updates(
    html: str,
    page_url: str,
    *,
    fetched_at: datetime,
    max_items: int = 30,
) -> list[LegislativeDocument]:
    soup = BeautifulSoup(html, "html.parser")
    documents: list[LegislativeDocument] = []
    for heading in soup.find_all(["h2", "h3"]):
        title = normalize_text(heading.get_text(" "))
        if not title:
            continue
        block_text = _following_block_text(heading)
        folded = fold_for_search(f"{title} {block_text}")
        if "banca dati" not in folded and "multivigenza" not in folded:
            continue
        source_url = _first_non_generic_link(heading, page_url) or page_url
        summary = _summary_from_block(block_text)
        raw_text = "\n\n".join(part for part in [title, summary] if part)
        documents.append(
            LegislativeDocument(
                source="Normattiva - aggiornamenti in multivigenza",
                source_type="html",
                level="nazionale",
                act_type=infer_act_type(raw_text),
                identifier=source_url,
                title=_clean_normattiva_title(title),
                summary=summary or None,
                date_published=_last_date_in_text(block_text),
                last_update=fetched_at,
                status="pubblicato",
                url=source_url,
                text=raw_text,
                metadata={
                    "connector": NormattivaConnector.name,
                    "page_source": page_url,
                    "kind": "multivigenza_update",
                    "accessed_at": fetched_at.isoformat(),
                },
            )
        )
        if len(documents) >= max_items:
            break
    return documents


def parse_approved_not_published_laws(
    html: str,
    page_url: str,
    *,
    fetched_at: datetime,
    max_items: int = 30,
) -> list[LegislativeDocument]:
    soup = BeautifulSoup(html, "html.parser")
    documents: list[LegislativeDocument] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        link_text = normalize_text(anchor.get_text(" "))
        if "Testo definitivamente approvato" not in link_text:
            continue
        source_url = urljoin(page_url, anchor["href"])
        if source_url in seen_urls:
            continue
        title = _previous_legislative_title(anchor) or link_text
        identifiers = _following_bill_identifiers(anchor)
        text = "\n\n".join(
            part
            for part in [
                title,
                link_text,
                f"Iter: {', '.join(identifiers)}" if identifiers else None,
            ]
            if part
        )
        documents.append(
            LegislativeDocument(
                source="Parlamento Italiano - leggi approvate non promulgate o pubblicate",
                source_type="html",
                level="nazionale",
                act_type="legge",
                identifier=", ".join(identifiers) if identifiers else source_url,
                title=title,
                summary=link_text,
                date_presented=parse_connector_date(link_text),
                last_update=fetched_at,
                status="approvato",
                url=source_url,
                text=text,
                metadata={
                    "connector": NormattivaConnector.name,
                    "page_source": page_url,
                    "kind": "approved_not_published",
                    "bill_identifiers": identifiers,
                    "accessed_at": fetched_at.isoformat(),
                },
            )
        )
        seen_urls.add(source_url)
        if len(documents) >= max_items:
            break
    return documents


def _following_block_text(node) -> str:
    parts: list[str] = []
    for sibling in node.next_siblings:
        if getattr(sibling, "name", None) in {"h2", "h3"}:
            break
        text = normalize_text(sibling.get_text(" ") if hasattr(sibling, "get_text") else str(sibling))
        if text:
            parts.append(text)
        if len(parts) >= 8:
            break
    return normalize_text(" ".join(parts))


def _first_non_generic_link(node, page_url: str) -> str | None:
    candidates = []
    for sibling in node.next_siblings:
        if getattr(sibling, "name", None) in {"h2", "h3"}:
            break
        if not hasattr(sibling, "find_all"):
            continue
        candidates.extend(sibling.find_all("a", href=True))
    for anchor in candidates:
        text = fold_for_search(anchor.get_text(" "))
        if "leggi di piu" in text:
            continue
        return urljoin(page_url, anchor["href"])
    for anchor in candidates:
        return urljoin(page_url, anchor["href"])
    return None


def _summary_from_block(block_text: str) -> str:
    parts = []
    for piece in block_text.split(" Leggi di"):
        cleaned = normalize_text(piece)
        if cleaned:
            parts.append(cleaned)
    return parts[0] if parts else normalize_text(block_text)


def _clean_normattiva_title(title: str) -> str:
    cleaned = normalize_text(title).strip('"')
    return cleaned or "Aggiornamento Normattiva"


def _previous_legislative_title(anchor) -> str:
    skip = {
        "parlamento italiano",
        "progetti di legge approvati non promulgati o pubblicati",
        "indici delle leggi",
        "leggi",
    }
    for previous in anchor.find_all_previous(string=True):
        text = normalize_text(str(previous))
        folded = fold_for_search(text)
        if not text or folded in skip:
            continue
        if "testo definitivamente approvato" in folded:
            continue
        if "iter e lavori preparatori" in folded:
            continue
        if len(text) < 12:
            continue
        return text.lstrip("* ").strip()
    return ""


def _following_bill_identifiers(anchor) -> list[str]:
    identifiers: list[str] = []
    current = anchor
    for _ in range(12):
        current = current.find_next()
        if current is None:
            break
        if getattr(current, "name", None) == "a":
            text = normalize_text(current.get_text(" "))
            if "Testo definitivamente approvato" in text:
                break
            if _looks_like_bill_identifier(text):
                identifiers.append(text)
    return identifiers


def _looks_like_bill_identifier(value: str) -> bool:
    folded = value.strip().upper()
    return bool(folded and len(folded) <= 20 and folded[0:2] in {"S.", "C."})


def _last_date_in_text(value: str):
    month_names = "|".join(ITALIAN_MONTHS)
    pattern = re.compile(
        rf"\b\d{{1,2}}\s+(?:{month_names})\s+\d{{4}}\b"
        r"|\b\d{4}-\d{1,2}-\d{1,2}\b"
        r"|\b\d{1,2}/\d{1,2}/\d{4}\b"
        r"|\b\d{8}\b",
        flags=re.I,
    )
    parsed_dates = [parse_connector_date(match.group(0)) for match in pattern.finditer(value)]
    parsed_dates = [item for item in parsed_dates if item is not None]
    return parsed_dates[-1] if parsed_dates else parse_connector_date(value)


def _bounded_limit(value: object) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 30
    return max(1, min(limit, 100))
