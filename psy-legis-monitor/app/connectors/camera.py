"""Connector for Camera dei deputati linked open data."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.http_fetch import fetch_text
from app.connectors.parsing import compact_identifier, first_non_blank, parse_connector_date
from app.connectors.sparql import sparql_query
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import normalize_text


CAMERA_ENDPOINT = "https://dati.camera.it/sparql"
CAMERA_LATEST_BILLS_URL = "https://www.camera.it/leg19/141"
DEFAULT_LEGISLATURE_URI = "http://dati.camera.it/ocd/legislatura.rdf/repubblica_19"


class CameraConnector(BaseConnector):
    """Fetch recent bills and proposals from dati.camera.it."""

    name = "camera"

    def __init__(
        self,
        *,
        endpoint_url: str | None = None,
        legislature_uri: str | None = None,
        limit: int | None = None,
        fetch_method: str | None = None,
        timeout: float | None = None,
        fallback_url: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        config = load_yaml(settings.sources_path).get("camera", {})
        self.enabled = config.get("enabled", True) if enabled is None else enabled
        self.endpoint_url = endpoint_url or config.get("endpoint_url", CAMERA_ENDPOINT)
        self.legislature_uri = legislature_uri or config.get("legislature_uri", DEFAULT_LEGISLATURE_URI)
        self.limit = _bounded_limit(limit if limit is not None else config.get("limit", 30))
        self.fetch_method = fetch_method or config.get("fetch_method", "auto")
        self.timeout = float(timeout if timeout is not None else config.get("timeout", 30))
        self.fallback_url = fallback_url or config.get("fallback_url", CAMERA_LATEST_BILLS_URL)

    def fetch_documents(self) -> list[LegislativeDocument]:
        if not self.enabled:
            return []
        fetched_at = datetime.now(UTC)
        sparql_error: Exception | None = None
        try:
            rows = sparql_query(
                self.endpoint_url,
                _build_camera_query(self.legislature_uri, self.limit),
                method=self.fetch_method,
                timeout=self.timeout,
            )
            documents = [_camera_row_to_document(row, fetched_at=fetched_at) for row in rows if row.get("title")]
            if documents:
                return documents
        except Exception as exc:
            sparql_error = exc

        html = fetch_text(self.fallback_url, method=self.fetch_method, timeout=self.timeout)
        documents = parse_camera_latest_bills(
            html,
            self.fallback_url,
            fetched_at=fetched_at,
            limit=self.limit,
            sparql_error=sparql_error,
        )
        if documents:
            return documents
        if sparql_error:
            raise RuntimeError(
                "Camera non interrogabile via SPARQL e fallback HTML senza risultati"
            ) from sparql_error
        return []


def _build_camera_query(legislature_uri: str, limit: int) -> str:
    return f"""
PREFIX ocd: <http://dati.camera.it/ocd/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX dct: <http://purl.org/dc/terms/>

SELECT DISTINCT ?atto ?title ?description ?date ?identifier ?type ?creator ?ref WHERE {{
  ?atto a ocd:atto ;
        dc:title ?title ;
        dc:date ?date ;
        ocd:rif_leg <{legislature_uri}> .
  OPTIONAL {{ ?atto dc:description ?description }}
  OPTIONAL {{ ?atto dc:identifier ?identifier }}
  OPTIONAL {{ ?atto dc:type ?type }}
  OPTIONAL {{ ?atto dc:creator ?creator }}
  OPTIONAL {{ ?atto dct:isReferencedBy ?ref }}
}}
ORDER BY DESC(?date)
LIMIT {limit}
""".strip()


def _camera_row_to_document(row: dict[str, str], *, fetched_at: datetime) -> LegislativeDocument:
    title = normalize_text(row["title"])
    description = normalize_text(row.get("description"))
    identifier = compact_identifier(first_non_blank(row.get("identifier"), _tail(row.get("atto"))))
    source_url = first_non_blank(row.get("ref"), row.get("atto"))
    presented = parse_connector_date(row.get("date"))
    text = "\n\n".join(
        part
        for part in [
            title,
            description,
            f"Identificativo: {identifier}" if identifier else None,
            f"Tipo fonte Camera: {row.get('type')}" if row.get("type") else None,
            f"Data: {row.get('date')}" if row.get("date") else None,
        ]
        if part
    )
    return LegislativeDocument(
        source="Camera dei deputati - Dati Camera",
        source_type="official_api",
        level="nazionale",
        act_type="proposta_di_legge",
        identifier=identifier,
        title=title,
        summary=description or None,
        date_presented=presented,
        last_update=fetched_at,
        status="presentato",
        url=source_url,
        text=text,
        metadata={
            "connector": CameraConnector.name,
            "atto_uri": row.get("atto"),
            "raw_date": row.get("date"),
            "camera_type": row.get("type"),
            "creator": row.get("creator"),
            "accessed_at": fetched_at.isoformat(),
        },
    )


def parse_camera_latest_bills(
    html: str,
    page_url: str,
    *,
    fetched_at: datetime,
    limit: int,
    sparql_error: Exception | None = None,
) -> list[LegislativeDocument]:
    soup = BeautifulSoup(html, "html.parser")
    documents: list[LegislativeDocument] = []
    seen: set[str] = set()
    links_by_identifier = _camera_bill_links_by_identifier(soup, page_url)

    for anchor in soup.find_all("a", href=True):
        identifier = compact_identifier(anchor.get_text(" "))
        if not _is_camera_bill_identifier(identifier):
            continue
        raw_text = _camera_latest_bill_context(anchor)
        title = _camera_latest_bill_title(raw_text, identifier)
        if not title:
            continue
        source_url = links_by_identifier.get(identifier, urljoin(page_url, str(anchor["href"])))
        dedupe_key = identifier or source_url
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        published = parse_connector_date(raw_text)
        documents.append(
            _camera_latest_bill_document(
                identifier=identifier,
                title=title,
                source_url=source_url,
                page_url=page_url,
                fetched_at=fetched_at,
                published=published,
                sparql_error=sparql_error,
            )
        )
        if len(documents) >= limit:
            break
    if documents:
        return documents

    page_text = normalize_text(soup.get_text(" "))
    for match in re.finditer(
        r"(?P<identifier>A\.?\s*C\.?\s*\d+)\s+(?P<title>.*?)(?:Stampato\s+il\s+)(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{4})",
        page_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        identifier = compact_identifier(match.group("identifier"))
        if not identifier:
            continue
        source_url = links_by_identifier.get(identifier, page_url)
        dedupe_key = identifier or source_url
        if dedupe_key in seen:
            continue
        title = _camera_latest_bill_title(match.group("title"), identifier)
        if not title:
            continue
        seen.add(dedupe_key)
        documents.append(
            _camera_latest_bill_document(
                identifier=identifier,
                title=title,
                source_url=source_url,
                page_url=page_url,
                fetched_at=fetched_at,
                published=parse_connector_date(match.group("date")),
                sparql_error=sparql_error,
            )
        )
        if len(documents) >= limit:
            break
    return documents


def _camera_bill_links_by_identifier(soup: BeautifulSoup, page_url: str) -> dict[str, str]:
    links: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        identifier = compact_identifier(anchor.get_text(" "))
        if _is_camera_bill_identifier(identifier) and identifier:
            links[identifier] = urljoin(page_url, str(anchor["href"]))
    return links


def _camera_latest_bill_document(
    *,
    identifier: str,
    title: str,
    source_url: str,
    page_url: str,
    fetched_at: datetime,
    published,
    sparql_error: Exception | None,
) -> LegislativeDocument:
    text = "\n\n".join(
        part
        for part in [
            title,
            f"Identificativo: {identifier}",
            f"Stampato il: {published.isoformat()}" if published else None,
        ]
        if part
    )
    metadata = {
        "connector": CameraConnector.name,
        "fallback": "camera_latest_bills_html",
        "container_url": page_url,
        "accessed_at": fetched_at.isoformat(),
    }
    if sparql_error:
        metadata["sparql_error"] = str(sparql_error)
    return LegislativeDocument(
        source="Camera dei deputati - Progetti di legge",
        source_type="html",
        level="nazionale",
        act_type="proposta_di_legge",
        identifier=identifier,
        title=title,
        summary=None,
        date_published=published,
        last_update=fetched_at,
        status="presentato",
        url=source_url,
        text=text,
        metadata=metadata,
    )


def _is_camera_bill_identifier(value: str | None) -> bool:
    return bool(value) and bool(re.match(r"^A\.?\s*C\.?\s*\d+", value, flags=re.IGNORECASE))


def _camera_latest_bill_context(anchor: Tag) -> str:
    container = anchor.find_parent("li")
    if container is not None:
        text = normalize_text(container.get_text(" "))
        if _camera_latest_bill_title(text, normalize_text(anchor.get_text(" "))):
            return text

    parts: list[str] = []
    for node in anchor.next_elements:
        if isinstance(node, Tag):
            if node is not anchor and node.name == "a" and _is_camera_bill_identifier(normalize_text(node.get_text(" "))):
                break
            continue
        if not isinstance(node, NavigableString):
            continue
        text = normalize_text(str(node))
        if not text:
            continue
        if re.search(r"\b(?:RICERCA PER NUMERO|FILTRA I PROGETTI DI LEGGE)\b", text, flags=re.IGNORECASE):
            break
        parts.append(text)
        if "Stampato il" in text or len(" ".join(parts)) > 1200:
            break
    return normalize_text(" ".join(parts))


def _camera_latest_bill_title(raw_text: str, identifier: str) -> str:
    title = re.sub(re.escape(identifier), " ", raw_text, flags=re.IGNORECASE)
    title = re.sub(r"\bStampato\s+il\s+\d{1,2}[-/]\d{1,2}[-/]\d{4}\b", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\(\s*\d+\s*\)\s*$", "", title)
    title = normalize_text(title).strip(" -:;,.")
    return title


def _tail(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").rsplit("/", 1)[-1].replace(".rdf", "")


def _bounded_limit(value: object) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 30
    return max(1, min(limit, 200))
