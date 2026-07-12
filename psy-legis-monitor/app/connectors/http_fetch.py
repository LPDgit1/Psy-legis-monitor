"""HTTP helpers shared by connectors."""

from __future__ import annotations

import subprocess
import sys

import httpx


def fetch_text(url: str, *, method: str = "auto", timeout: float = 30) -> str:
    """Fetch text with a Windows-friendly PowerShell fallback."""

    selected_method = method
    if selected_method == "auto":
        selected_method = "powershell" if sys.platform.startswith("win") else "httpx"
    if selected_method == "powershell":
        return _fetch_text_with_powershell(url, timeout=timeout)
    return _fetch_text_with_httpx(url, timeout=timeout)


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
