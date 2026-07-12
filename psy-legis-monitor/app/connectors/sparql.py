"""SPARQL helpers for official linked-open-data connectors."""

from __future__ import annotations

from urllib.parse import urlencode
from xml.etree import ElementTree

from app.connectors.http_fetch import fetch_text
from app.core.text_cleaning import normalize_text


SPARQL_NS = {"sparql": "http://www.w3.org/2005/sparql-results#"}


def sparql_query(
    endpoint_url: str,
    query: str,
    *,
    method: str = "auto",
    timeout: float = 30,
) -> list[dict[str, str]]:
    """Run a SPARQL SELECT query and parse W3C SPARQL XML results."""

    params = urlencode({"query": query, "format": "xml"})
    separator = "&" if "?" in endpoint_url else "?"
    payload = fetch_text(f"{endpoint_url}{separator}{params}", method=method, timeout=timeout)
    return parse_sparql_xml(payload)


def parse_sparql_xml(payload: str) -> list[dict[str, str]]:
    root = ElementTree.fromstring(payload)
    rows: list[dict[str, str]] = []
    for result in root.findall(".//sparql:result", SPARQL_NS):
        row: dict[str, str] = {}
        for binding in result.findall("sparql:binding", SPARQL_NS):
            name = binding.attrib.get("name")
            if not name:
                continue
            value = _binding_value(binding)
            if value is not None:
                row[name] = value
        if row:
            rows.append(row)
    return rows


def _binding_value(binding: ElementTree.Element) -> str | None:
    for child in list(binding):
        if child.text is None:
            continue
        text = normalize_text(child.text)
        if text:
            return text
    return None
