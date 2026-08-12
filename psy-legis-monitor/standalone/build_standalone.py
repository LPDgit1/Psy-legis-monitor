"""Embed the latest public catalogue into the offline standalone HTML."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "psy-legis-monitor-standalone.template.html"
OUTPUT = ROOT / "psy-legis-monitor-standalone.html"
SNAPSHOT = ROOT.parent / "data" / "public_documents.json"
MARKER = "__PUBLIC_SNAPSHOT_JSON__"


def main() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    documents = payload.get("documents")
    if payload.get("schema_version") != 1 or not isinstance(documents, list) or not documents:
        raise RuntimeError("La snapshot pubblica non e valida o non contiene documenti.")
    if payload.get("published_document_count") != len(documents):
        raise RuntimeError("Il conteggio della snapshot non coincide con i documenti incorporati.")

    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(MARKER) != 1:
        raise RuntimeError("Il template standalone deve contenere un solo marcatore dati.")
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    OUTPUT.write_text(template.replace(MARKER, serialized), encoding="utf-8", newline="\n")
    print(f"Standalone creato: {OUTPUT} ({len(documents)} atti)")


if __name__ == "__main__":
    main()
