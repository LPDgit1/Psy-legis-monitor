"""Validated last-known-good snapshots for the Camera connector."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Iterable, Mapping

from app.connectors.parsing import parse_connector_date
from app.core.text_cleaning import normalize_text


CAMERA_SNAPSHOT_SCHEMA_VERSION = 1
CAMERA_QUERY_VERSION = 2
CAMERA_SNAPSHOT_SOURCE = "dati.camera.it"
CAMERA_ROW_FIELDS = ("atto", "title", "date", "identifier")


class CameraSnapshotError(RuntimeError):
    """Raised when a Camera snapshot is absent or invalid."""


def build_camera_snapshot(
    rows: Iterable[Mapping[str, object]],
    *,
    endpoint_url: str,
    legislature_uri: str,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Build and validate a deterministic Camera snapshot payload."""

    normalized_rows = _normalize_rows(rows)
    if not normalized_rows:
        raise CameraSnapshotError("La risposta Camera non contiene atti utilizzabili.")

    endpoint = normalize_text(endpoint_url)
    legislature = normalize_text(legislature_uri)
    if not endpoint.startswith("https://"):
        raise CameraSnapshotError("Endpoint della snapshot Camera non valido.")
    if not legislature.startswith(("http://", "https://")):
        raise CameraSnapshotError("Legislatura della snapshot Camera non valida.")

    generated = _as_utc(generated_at or datetime.now(UTC))
    return {
        "schema_version": CAMERA_SNAPSHOT_SCHEMA_VERSION,
        "query_version": CAMERA_QUERY_VERSION,
        "source": CAMERA_SNAPSHOT_SOURCE,
        "endpoint_url": endpoint,
        "legislature_uri": legislature,
        "generated_at": generated.isoformat().replace("+00:00", "Z"),
        "result_count": len(normalized_rows),
        "newest_identifier": normalized_rows[0]["identifier"],
        "newest_date": normalized_rows[0]["date"],
        "rows": normalized_rows,
    }


def write_camera_snapshot(
    rows: Iterable[Mapping[str, object]],
    path: str | Path,
    *,
    endpoint_url: str,
    legislature_uri: str,
    generated_at: datetime | None = None,
    minimum_result_count: int = 1,
    minimum_retained_ratio: float = 0.8,
) -> dict[str, object]:
    """Atomically replace a snapshot only after the new payload validates."""

    payload = build_camera_snapshot(
        rows,
        endpoint_url=endpoint_url,
        legislature_uri=legislature_uri,
        generated_at=generated_at,
    )
    target = Path(path)
    _validate_snapshot_replacement(
        payload,
        target,
        minimum_result_count=minimum_result_count,
        minimum_retained_ratio=minimum_retained_ratio,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        temporary.write_text(serialized, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return payload


def load_camera_snapshot(path: str | Path) -> dict[str, object]:
    """Read a snapshot and reject incomplete, stale-schema, or inconsistent data."""

    target = Path(path)
    if not target.exists():
        raise CameraSnapshotError("Snapshot Camera non ancora disponibile.")
    try:
        raw_payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CameraSnapshotError("Snapshot Camera non leggibile o JSON non valido.") from exc
    if not isinstance(raw_payload, dict):
        raise CameraSnapshotError("Snapshot Camera con struttura non valida.")
    if raw_payload.get("schema_version") != CAMERA_SNAPSHOT_SCHEMA_VERSION:
        raise CameraSnapshotError("Versione della snapshot Camera non supportata.")
    if raw_payload.get("query_version") != CAMERA_QUERY_VERSION:
        raise CameraSnapshotError("Snapshot Camera prodotta da una query non supportata.")
    if normalize_text(raw_payload.get("source")) != CAMERA_SNAPSHOT_SOURCE:
        raise CameraSnapshotError("Snapshot Camera con fonte non riconosciuta.")
    if not normalize_text(raw_payload.get("endpoint_url")).startswith("https://"):
        raise CameraSnapshotError("Snapshot Camera con endpoint non valido.")
    if not normalize_text(raw_payload.get("legislature_uri")).startswith(("http://", "https://")):
        raise CameraSnapshotError("Snapshot Camera con legislatura non valida.")

    generated_at = _parse_snapshot_datetime(raw_payload.get("generated_at"))
    raw_rows = raw_payload.get("rows")
    if not isinstance(raw_rows, list):
        raise CameraSnapshotError("Snapshot Camera senza elenco degli atti.")
    normalized_rows = _normalize_rows(raw_rows, reject_duplicates=True)
    if not normalized_rows:
        raise CameraSnapshotError("Snapshot Camera priva di atti utilizzabili.")
    if raw_payload.get("result_count") != len(normalized_rows):
        raise CameraSnapshotError("Conteggio della snapshot Camera incoerente.")
    if normalize_text(raw_payload.get("newest_identifier")) != normalized_rows[0]["identifier"]:
        raise CameraSnapshotError("Identificativo piu recente della snapshot Camera incoerente.")
    if normalize_text(raw_payload.get("newest_date")) != normalized_rows[0]["date"]:
        raise CameraSnapshotError("Data piu recente della snapshot Camera incoerente.")

    payload = dict(raw_payload)
    payload["generated_at"] = generated_at.isoformat().replace("+00:00", "Z")
    payload["rows"] = normalized_rows
    return payload


def camera_snapshot_status(path: str | Path, *, max_age_hours: float) -> dict[str, object]:
    """Return a compact status suitable for the dashboard, without network access."""

    target = Path(path)
    try:
        payload = load_camera_snapshot(target)
    except CameraSnapshotError as exc:
        return {
            "diagnostic_schema_version": 10,
            "mode": "snapshot",
            "snapshot_status": "missing" if not target.exists() else "invalid",
            "snapshot_file": target.name,
            "message": str(exc),
        }

    generated_at = _parse_snapshot_datetime(payload["generated_at"])
    age_hours = max(0.0, (datetime.now(UTC) - generated_at).total_seconds() / 3600)
    status = "stale" if age_hours > max_age_hours else "ok"
    return {
        "diagnostic_schema_version": 10,
        "mode": "snapshot",
        "snapshot_status": status,
        "snapshot_file": target.name,
        "generated_at": payload["generated_at"],
        "age_hours": round(age_hours, 1),
        "max_age_hours": max_age_hours,
        "result_count": payload["result_count"],
        "newest_identifier": payload["newest_identifier"],
        "newest_date": payload["newest_date"],
    }


def parse_snapshot_generated_at(value: object) -> datetime:
    """Expose the validated snapshot timestamp for document normalization."""

    return _parse_snapshot_datetime(value)


def _normalize_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    reject_duplicates: bool = False,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen_acts: set[str] = set()
    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            raise CameraSnapshotError("Snapshot Camera con una riga non valida.")
        row = {field: normalize_text(raw_row.get(field)) for field in CAMERA_ROW_FIELDS}
        missing = [field for field, value in row.items() if not value]
        if missing:
            raise CameraSnapshotError(
                "Riga Camera incompleta: mancano " + ", ".join(sorted(missing)) + "."
            )
        if not row["atto"].startswith(("http://", "https://")):
            raise CameraSnapshotError("URI di un atto Camera non valido.")
        if parse_connector_date(row["date"]) is None:
            raise CameraSnapshotError("Data di un atto Camera non valida.")
        if row["atto"] in seen_acts:
            if reject_duplicates:
                raise CameraSnapshotError("Snapshot Camera con atti duplicati.")
            continue
        seen_acts.add(row["atto"])
        normalized.append(row)
    return sorted(normalized, key=_row_sort_key, reverse=True)


def _row_sort_key(row: Mapping[str, str]) -> tuple[str, int, str]:
    digits = re.findall(r"\d+", row["identifier"])
    numeric_identifier = int(digits[-1]) if digits else -1
    return row["date"], numeric_identifier, row["identifier"]


def _validate_snapshot_replacement(
    payload: Mapping[str, object],
    target: Path,
    *,
    minimum_result_count: int,
    minimum_retained_ratio: float,
) -> None:
    result_count = int(payload["result_count"])
    if result_count < max(1, minimum_result_count):
        raise CameraSnapshotError(
            f"Snapshot Camera con soli {result_count} atti; minimo richiesto {minimum_result_count}."
        )
    if not 0 <= minimum_retained_ratio <= 1:
        raise CameraSnapshotError("Rapporto minimo di conservazione Camera non valido.")
    if not target.exists():
        return
    try:
        previous = load_camera_snapshot(target)
    except CameraSnapshotError:
        return
    previous_count = int(previous["result_count"])
    minimum_from_previous = ceil(previous_count * minimum_retained_ratio)
    if result_count < minimum_from_previous:
        raise CameraSnapshotError(
            "La nuova snapshot Camera ha perso troppe righe rispetto all'ultima versione valida."
        )
    if str(payload["newest_date"]) < str(previous["newest_date"]):
        raise CameraSnapshotError(
            "La nuova snapshot Camera arretra rispetto alla data piu recente gia acquisita."
        )


def _parse_snapshot_datetime(value: object) -> datetime:
    text = normalize_text(value)
    if not text:
        raise CameraSnapshotError("Snapshot Camera senza data di generazione.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CameraSnapshotError("Data di generazione della snapshot Camera non valida.") from exc
    if parsed.tzinfo is None:
        raise CameraSnapshotError("Data della snapshot Camera priva di fuso orario.")
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise CameraSnapshotError("La data della snapshot Camera deve includere il fuso orario.")
    return value.astimezone(UTC)
