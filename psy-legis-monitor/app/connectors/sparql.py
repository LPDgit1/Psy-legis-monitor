"""SPARQL helpers for official linked-open-data connectors."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx

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

    errors: list[Exception] = []
    if _should_try_httpx_post(method):
        try:
            return _sparql_post_json(endpoint_url, query, timeout=timeout)
        except Exception as exc:
            errors.append(exc)
    if _should_try_powershell_post(method):
        try:
            return _sparql_post_json_with_powershell(endpoint_url, query, timeout=timeout)
        except Exception as exc:
            errors.append(exc)

    separator = "&" if "?" in endpoint_url else "?"

    for response_format, parser in [
        ("json", parse_sparql_json),
        ("application/sparql-results+json", parse_sparql_json),
        ("xml", parse_sparql_xml),
    ]:
        params = urlencode({"query": query, "format": response_format})
        payload = fetch_text(f"{endpoint_url}{separator}{params}", method=method, timeout=timeout)
        try:
            return parser(payload)
        except ValueError as exc:
            errors.append(exc)

    detail = "; ".join(str(error) for error in errors[-5:])
    raise RuntimeError(f"Endpoint SPARQL non ha restituito risultati JSON/XML validi. {detail}")


def _should_try_httpx_post(method: str) -> bool:
    return method in {"auto", "httpx"}


def _should_try_powershell_post(method: str) -> bool:
    return method in {"auto", "powershell"} and _powershell_executable() is not None


def _sparql_post_json(endpoint_url: str, query: str, *, timeout: float) -> list[dict[str, str]]:
    headers = {
        "Accept": "application/sparql-results+json, application/json;q=0.9, */*;q=0.1",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "psy-legis-monitor/0.1 (+institutional monitoring)",
    }
    errors: list[Exception] = []
    for response_format in ("application/sparql-results+json", "json"):
        response = httpx.post(
            endpoint_url,
            data={"query": query, "format": response_format},
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        try:
            return parse_sparql_json(response.text)
        except ValueError as exc:
            errors.append(exc)
    detail = "; ".join(str(error) for error in errors[-2:])
    raise RuntimeError(f"POST SPARQL non ha restituito JSON valido. {detail}")


def _sparql_post_json_with_powershell(endpoint_url: str, query: str, *, timeout: float) -> list[dict[str, str]]:
    executable = _powershell_executable()
    if executable is None:
        raise RuntimeError("PowerShell non disponibile per POST SPARQL")
    escaped_url = endpoint_url.replace("'", "''")
    timeout_seconds = max(1, int(timeout))
    command = [
        executable,
        "-NoProfile",
        "-Command",
        "$ProgressPreference='SilentlyContinue'; "
        "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; "
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
        "$query=$env:PSY_LEGIS_SPARQL_QUERY; "
        f"$url='{escaped_url}'; "
        "$body=@{ query=$query; format='application/sparql-results+json' }; "
        "$headers=@{ Accept='application/sparql-results+json, application/json;q=0.9'; "
        "'User-Agent'='psy-legis-monitor/0.1 (+institutional monitoring)' }; "
        f"$response=Invoke-WebRequest -UseBasicParsing -Uri $url -Method Post -Body $body -Headers $headers -TimeoutSec {timeout_seconds}; "
        "if ($response.Content -is [byte[]]) { "
        "[System.Text.Encoding]::UTF8.GetString($response.Content) "
        "} else { [string]$response.Content }",
    ]
    env = os.environ.copy()
    env["PSY_LEGIS_SPARQL_QUERY"] = query
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    return parse_sparql_json(completed.stdout)


def _powershell_executable() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")


def parse_sparql_json(payload: str) -> list[dict[str, str]]:
    if _looks_like_html(payload):
        raise ValueError(_html_payload_message(payload, "JSON"))
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        snippet = normalize_text(payload[:200])
        raise ValueError(f"Risposta SPARQL JSON non valida. Inizio risposta: {snippet}") from exc

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
    if _looks_like_html(payload):
        raise ValueError(_html_payload_message(payload, "XML"))
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


def _looks_like_html(payload: str) -> bool:
    prefix = payload.lstrip()[:200].lower()
    return prefix.startswith("<!doctype html") or prefix.startswith("<html") or "<html" in prefix


def _html_payload_message(payload: str, expected_format: str) -> str:
    snippet = normalize_text(payload[:200])
    return (
        f"Risposta SPARQL in HTML invece che {expected_format}: "
        f"probabile pagina tecnica/cache dell'endpoint. Inizio risposta: {snippet}"
    )


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
