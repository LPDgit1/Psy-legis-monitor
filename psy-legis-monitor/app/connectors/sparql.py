"""SPARQL helpers for official linked-open-data connectors."""

from __future__ import annotations

import json
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
    """Run a SPARQL SELECT query and parse W3C SPARQL results."""

    params = urlencode({"query": query, "format": "json"})
    separator = "&" if "?" in endpoint_url else "?"
    payload = fetch_text(f"{endpoint_url}{separator}{params}", method=method, timeout=timeout)
    try:
        return parse_sparql_json(payload)
    except ValueError:
        # Some SPARQL endpoints ignore the requested format and still return XML.
        try:
            return parse_sparql_xml(payload)
        except ValueError:
            params = urlencode({"query": query, "format": "xml"})
            payload = fetch_text(f"{endpoint_url}{separator}{params}", method=method, timeout=timeout)
            return parse_sparql_xml(payload)


def parse_sparql_json(payload: str) -> list[dict[str, str]]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Risposta SPARQL JSON non valida") from exc

    bindings = data.get("results", {}).get("bindings", [])
    if not isinstance(bindings, list):
        raise ValueError("Risposta SPARQL JSON senza results.bindings")

    rows: list[dict[str, str]] = []
    for result in bindings:
        if not isinstance(result, dict):
            continue
        row: dict[str, str] = {}
        for name, binding in result.items():
            if not isinstance(binding, dict):
                continue
            value = binding.get("value")
            if value is None:
                continue
            text = normalize_text(str(value))
            if text:
                row[name] = text
        if row:
            rows.append(row)
    return rows


def parse_sparql_xml(payload: str) -> list[dict[str, str]]:
    try:
        root = ElementTree.fromstring(_strip_invalid_xml_chars(payload))
    except ElementTree.ParseError as exc:
        snippet = normalize_text(payload[:200])
        raise ValueError(f"Risposta SPARQL XML non valida: {exc}. Inizio risposta: {snippet}") from exc

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


def _strip_invalid_xml_chars(value: str) -> str:
    return "".join(ch for ch in value if _is_valid_xml_char(ch))


def _is_valid_xml_char(ch: str) -> bool:
    codepoint = ord(ch)
    return (
        codepoint in (0x09, 0x0A, 0x0D)
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def _binding_value(binding: ElementTree.Element) -> str | None:
    for child in list(binding):
        if child.text is None:
            continue
        text = normalize_text(child.text)
        if text:
            return text
    return None
