"""HTTP helpers shared by connectors."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import httpx


def fetch_text(url: str, *, method: str = "auto", timeout: float = 30) -> str:
    """Fetch text with a Windows-friendly PowerShell fallback."""

    selected_method = method
    if selected_method == "auto":
        selected_method = "powershell" if sys.platform.startswith("win") else "httpx"
    if selected_method == "powershell":
        return _fetch_text_with_powershell(url, timeout=timeout)
    return _fetch_text_with_httpx(url, timeout=timeout)


def fetch_bytes(
    url: str,
    *,
    method: str = "auto",
    timeout: float = 30,
    max_bytes: int = 20_000_000,
) -> bytes:
    """Fetch a bounded binary payload for official PDFs and attachments."""

    selected_method = method
    if selected_method == "auto":
        selected_method = "powershell" if sys.platform.startswith("win") else "httpx"
    if selected_method == "powershell":
        return _fetch_bytes_with_powershell(url, timeout=timeout, max_bytes=max_bytes)

    headers = {"User-Agent": "psy-legis-monitor/0.1 (+institutional monitoring)"}
    chunks: list[bytes] = []
    size = 0
    with httpx.stream(
        "GET",
        url,
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
    ) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise RuntimeError(f"Payload oltre il limite di {max_bytes} byte: {url}")
            chunks.append(chunk)
    return b"".join(chunks)


def _fetch_bytes_with_powershell(url: str, *, timeout: float, max_bytes: int) -> bytes:
    escaped_url = url.replace("'", "''")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
            temporary_path = Path(handle.name)
        escaped_path = str(temporary_path).replace("'", "''")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"$url='{escaped_url}'; $out='{escaped_path}'; $max={max_bytes}; "
            "$ProgressPreference='SilentlyContinue'; "
            "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; "
            "$head=Invoke-WebRequest -UseBasicParsing -Method Head -Uri $url; "
            "if ($head.Headers['Content-Length'] -and "
            "[long]$head.Headers['Content-Length'] -gt $max) { throw 'Payload oltre il limite' }; "
            "Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $out",
        ]
        subprocess.run(command, check=True, capture_output=True, timeout=timeout)
        if temporary_path.stat().st_size > max_bytes:
            raise RuntimeError(f"Payload oltre il limite di {max_bytes} byte: {url}")
        return temporary_path.read_bytes()
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


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
        "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; "
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
