"""Export helpers."""

from __future__ import annotations

from pathlib import Path


def export_markdown_report(markdown: str, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path

