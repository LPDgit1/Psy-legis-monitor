"""Connector for Camera dei deputati linked open data."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.http_fetch import fetch_text
from app.connectors.parsing import compact_identifier, first_non_blank, parse_connector_date
from app.connectors.sparql import SPARQL_USER_AGENT, sparql_query
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import normalize_text


CAMERA_ENDPOINT = "https://dati.camera.it/sparql"
CAMERA_LATEST_BILLS_URL = "https://www.camera.it/leg19/141"
DEFAULT_LEGISLATURE_URI = "http://dati.camera.it/ocd/legislatura.rdf/repubblica_19"
RDF_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}


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
        resource_fallback_enabled: bool | None = None,
        resource_probe_start: int | None = None,
        resource_probe_max: int | None = None,
        resource_probe_empty_stop: int | None = None,
    ) -> None:
        config = load_yaml(settings.sources_path).get("camera", {})
        self.enabled = config.get("enabled", True) if enabled is None else enabled
        self.endpoint_url = endpoint_url or config.get("endpoint_url", CAMERA_ENDPOINT)
        self.legislature_uri = legislature_uri or config.get("legislature_uri", DEFAULT_LEGISLATURE_URI)
        self.limit = _bounded_limit(limit if limit is not None else config.get("limit", 30))
        self.fetch_method = fetch_method or config.get("fetch_method", "auto")
        self.timeout = float(timeout if timeout is not None else config.get("timeout", 30))
        self.fallback_url = fallback_url or config.get("fallback_url", CAMERA_LATEST_BILLS_URL)
        self.resource_fallback_enabled = (
            config.get("resource_fallback_enabled", True)
            if resource_fallback_enabled is None
            else resource_fallback_enabled
        )
        self.resource_probe_start = _bounded_probe_number(
            resource_probe_start if resource_probe_start is not None else config.get("resource_probe_start", 2950)
        )
        self.resource_probe_max = _bounded_limit(
            resource_probe_max if resource_probe_max is not None else config.get("resource_probe_max", 180)
        )
        self.resource_probe_empty_stop = _bounded_limit(
            resource_probe_empty_stop
            if resource_probe_empty_stop is not None
            else config.get("resource_probe_empty_stop", 35)
        )

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

        if self.resource_fallback_enabled:
            try:
                documents = fetch_camera_resource_documents(
                    legislature_uri=self.legislature_uri,
                    start=self.resource_probe_start,
                    max_resources=self.resource_probe_max,
                    empty_stop=self.resource_probe_empty_stop,
                    limit=self.limit,
                    timeout=self.timeout,
                    fetched_at=fetched_at,
                    sparql_error=sparql_error,
                )
                if documents:
                    return documents
            except Exception:
                pass

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
        return []

    def diagnose_fetch(self) -> dict[str, object]:
        diagnostics: dict[str, object] = {
            "diagnostic_schema_version": 8,
            "endpoint_url": self.endpoint_url,
            "fallback_url": self.fallback_url,
            "fetch_method": self.fetch_method,
            "sparql_status": "not_checked",
            "fallback_status": "not_checked",
            "resource_status": "not_checked",
            "overall_status": "diagnostica avviata",
        }
        try:
            rows = sparql_query(
                self.endpoint_url,
                _build_camera_query(self.legislature_uri, min(self.limit, 3)),
                method=self.fetch_method,
                timeout=self.timeout,
            )
            diagnostics.update(
                {
                    "sparql_status": "ok" if rows else "ok_empty",
                    "sparql_rows": len(rows),
                    "sparql_sample_title": normalize_text(rows[0].get("title")) if rows else "",
                    "sparql_sample_identifier": compact_identifier(rows[0].get("identifier")) if rows else "",
                }
            )
        except Exception as exc:
            diagnostics["sparql_status"] = "error"
            diagnostics["sparql_error"] = str(exc)

        if diagnostics["sparql_status"] != "ok" and self.resource_fallback_enabled:
            try:
                resource_stats: dict[str, int] = {}
                resource_documents = fetch_camera_resource_documents(
                    legislature_uri=self.legislature_uri,
                    start=self.resource_probe_start,
                    max_resources=min(self.resource_probe_max, 80),
                    empty_stop=min(self.resource_probe_empty_stop, 20),
                    limit=min(self.limit, 3),
                    timeout=self.timeout,
                    fetched_at=datetime.now(UTC),
                    sparql_error=None,
                    stats=resource_stats,
                )
                diagnostics.update(
                    {
                        "resource_status": _camera_resource_status(resource_documents, resource_stats),
                        "resource_rows": len(resource_documents),
                        "resource_probe_start": self.resource_probe_start,
                        "resource_probe_max": min(self.resource_probe_max, 80),
                        "resource_probe_http_errors": resource_stats.get("http_errors", 0),
                        "resource_probe_html_payloads": resource_stats.get("html_payloads", 0),
                        "resource_probe_invalid_payloads": resource_stats.get("invalid_payloads", 0),
                        "resource_probe_empty_payloads": resource_stats.get("empty_payloads", 0),
                        "resource_sample_identifier": resource_documents[0].identifier
                        if resource_documents
                        else "",
                        "resource_sample_title": resource_documents[0].title if resource_documents else "",
                    }
                )
            except Exception as exc:
                diagnostics["resource_status"] = "error"
                diagnostics["resource_error"] = str(exc)

        try:
            html = fetch_text(self.fallback_url, method=self.fetch_method, timeout=self.timeout)
        except Exception as exc:
            diagnostics["fallback_status"] = "error"
            diagnostics["fallback_error"] = str(exc)
            diagnostics["overall_status"] = _camera_diagnostic_status(diagnostics)
            return diagnostics

        soup = BeautifulSoup(html, "html.parser")
        text = normalize_text(soup.get_text(" "))
        browser_check = _is_camera_browser_check_text(text)
        documents = parse_camera_latest_bills(
            html,
            self.fallback_url,
            fetched_at=datetime.now(UTC),
            limit=self.limit,
        )
        diagnostics.update(
            {
                "fallback_status": "blocked_by_browser_check"
                if browser_check
                else ("ok" if documents else "ok_no_documents"),
                "fallback_html_length": len(html),
                "fallback_title": normalize_text(soup.title.get_text(" ")) if soup.title else "",
                "blocked_by_browser_check": browser_check,
                "contains_ac_marker": bool(re.search(r"\bA\.?\s*C\.?\s*\d+", text, flags=re.IGNORECASE)),
                "ac_marker_count": len(re.findall(r"\bA\.?\s*C\.?\s*\d+", text, flags=re.IGNORECASE)),
                "parsed_documents": len(documents),
                "sample_text": text[:500],
            }
        )
        diagnostics["overall_status"] = _camera_diagnostic_status(diagnostics)
        return diagnostics


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


def fetch_camera_resource_documents(
    *,
    legislature_uri: str,
    start: int,
    max_resources: int,
    empty_stop: int,
    limit: int,
    timeout: float,
    fetched_at: datetime,
    sparql_error: Exception | None = None,
    stats: dict[str, int] | None = None,
) -> list[LegislativeDocument]:
    legislature = _legislature_number(legislature_uri)
    documents: list[LegislativeDocument] = []
    empty_seen = 0
    stats = stats if stats is not None else {}
    for number in range(start, start + max_resources):
        resource_url = f"https://dati.camera.it/ocd/attocamera.rdf/ac{legislature}_{number}"
        stats["probed"] = stats.get("probed", 0) + 1
        try:
            payload = _fetch_camera_resource_text(resource_url, timeout=timeout)
        except httpx.HTTPError:
            stats["http_errors"] = stats.get("http_errors", 0) + 1
            empty_seen += 1
            if documents and empty_seen >= empty_stop:
                break
            continue
        try:
            document = parse_camera_resource_rdf(
                payload,
                resource_url,
                fetched_at=fetched_at,
                sparql_error=sparql_error,
            )
        except CameraResourceHTMLPayload:
            stats["html_payloads"] = stats.get("html_payloads", 0) + 1
            empty_seen += 1
            if documents and empty_seen >= empty_stop:
                break
            continue
        except RuntimeError:
            stats["invalid_payloads"] = stats.get("invalid_payloads", 0) + 1
            empty_seen += 1
            if documents and empty_seen >= empty_stop:
                break
            continue
        if document is None:
            stats["empty_payloads"] = stats.get("empty_payloads", 0) + 1
            empty_seen += 1
            if documents and empty_seen >= empty_stop:
                break
            continue
        documents.append(document)
        empty_seen = 0

    documents.sort(
        key=lambda document: (
            document.date_presented or document.date_published or date.min,
            _identifier_number(document.identifier),
        ),
        reverse=True,
    )
    return documents[:limit]


class CameraResourceHTMLPayload(RuntimeError):
    """Raised when an RDF resource endpoint returns a technical HTML page."""


def parse_camera_resource_rdf(
    payload: str,
    resource_url: str,
    *,
    fetched_at: datetime,
    sparql_error: Exception | None = None,
) -> LegislativeDocument | None:
    if _looks_like_html(payload):
        raise CameraResourceHTMLPayload("Risorsa RDF Camera ha restituito HTML invece che RDF/XML")
    try:
        root = ElementTree.fromstring(payload.strip())
    except ElementTree.ParseError as exc:
        raise RuntimeError(f"Risorsa RDF Camera non valida: {exc}") from exc

    description = root.find(".//rdf:Description", RDF_NS)
    if description is None:
        return None
    row = {
        "atto": description.attrib.get(f"{{{RDF_NS['rdf']}}}about", resource_url),
        "title": _rdf_text(description, "dc:title"),
        "date": _rdf_text(description, "dc:date"),
        "identifier": _rdf_text(description, "dc:identifier"),
        "type": _rdf_text(description, "dc:type"),
        "creator": _rdf_text(description, "dc:creator"),
        "ref": _rdf_resource(description, "dcterms:isReferencedBy"),
    }
    if not row["title"] or not row["date"]:
        return None
    document = _camera_row_to_document(row, fetched_at=fetched_at)
    document.metadata["fallback"] = "camera_resource_rdf"
    document.metadata["resource_url"] = resource_url
    if sparql_error:
        document.metadata["sparql_error"] = str(sparql_error)
    return document


def _fetch_camera_resource_text(url: str, *, timeout: float) -> str:
    response = httpx.get(
        url,
        headers={"Accept": "application/rdf+xml", "User-Agent": SPARQL_USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _rdf_text(description: ElementTree.Element, path: str) -> str:
    found = description.find(path, RDF_NS)
    return normalize_text(found.text) if found is not None and found.text else ""


def _rdf_resource(description: ElementTree.Element, path: str) -> str:
    found = description.find(path, RDF_NS)
    if found is None:
        return ""
    return normalize_text(found.attrib.get(f"{{{RDF_NS['rdf']}}}resource"))


def _looks_like_html(payload: str) -> bool:
    prefix = payload.lstrip()[:200].lower()
    return prefix.startswith("<!doctype html") or prefix.startswith("<html") or "<html" in prefix


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


def _is_camera_browser_check_text(text: str) -> bool:
    folded = normalize_text(text).lower()
    return "checking your browser before accessing" in folded or "your browser will redirect" in folded


def _camera_diagnostic_status(diagnostics: dict[str, object]) -> str:
    sparql_status = diagnostics.get("sparql_status")
    resource_status = diagnostics.get("resource_status")
    fallback_status = diagnostics.get("fallback_status")
    if sparql_status == "ok" and fallback_status == "blocked_by_browser_check":
        return "ok: dati.camera.it SPARQL raggiungibile; fallback HTML www.camera.it bloccato ma non necessario"
    if sparql_status == "ok":
        return "ok: dati.camera.it SPARQL raggiungibile"
    if sparql_status == "error" and resource_status == "ok" and fallback_status == "blocked_by_browser_check":
        return "ok: SPARQL bloccato, ma fallback RDF ufficiale dati.camera.it raggiungibile; fallback HTML bloccato"
    if sparql_status == "error" and resource_status == "ok":
        return "ok: SPARQL bloccato, ma fallback RDF ufficiale dati.camera.it raggiungibile"
    if sparql_status == "error" and resource_status == "html_blocked":
        return "errore: SPARQL e risorse RDF Camera restituiscono HTML tecnico; fallback HTML bloccato"
    if sparql_status == "ok_empty":
        return "attenzione: dati.camera.it SPARQL raggiungibile ma senza risultati per la query"
    if sparql_status == "error" and fallback_status == "blocked_by_browser_check":
        return "errore: SPARQL non raggiungibile e fallback HTML bloccato da browser-check"
    if sparql_status == "error":
        return "errore: dati.camera.it SPARQL non raggiungibile"
    return "attenzione: diagnostica Camera incompleta"


def _camera_resource_status(documents: list[LegislativeDocument], stats: dict[str, int]) -> str:
    if documents:
        return "ok"
    if stats.get("html_payloads", 0) > 0:
        return "html_blocked"
    if stats.get("invalid_payloads", 0) > 0:
        return "invalid_payloads"
    return "ok_empty"


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


def _legislature_number(legislature_uri: str) -> int:
    match = re.search(r"repubblica_(\d+)", legislature_uri)
    if not match:
        return 19
    return int(match.group(1))


def _identifier_number(identifier: str | None) -> int:
    match = re.search(r"\d+", identifier or "")
    return int(match.group(0)) if match else 0


def _bounded_probe_number(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 2950
    return max(1, min(number, 20000))


def _bounded_limit(value: object) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 30
    return max(1, min(limit, 200))
