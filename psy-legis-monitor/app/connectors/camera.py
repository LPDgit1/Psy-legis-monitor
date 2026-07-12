"""Connector for Camera dei deputati linked open data."""

from __future__ import annotations

from datetime import UTC, datetime

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.parsing import compact_identifier, first_non_blank, parse_connector_date
from app.connectors.sparql import sparql_query
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import normalize_text


CAMERA_ENDPOINT = "https://dati.camera.it/sparql"
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
        enabled: bool | None = None,
    ) -> None:
        config = load_yaml(settings.sources_path).get("camera", {})
        self.enabled = config.get("enabled", True) if enabled is None else enabled
        self.endpoint_url = endpoint_url or config.get("endpoint_url", CAMERA_ENDPOINT)
        self.legislature_uri = legislature_uri or config.get("legislature_uri", DEFAULT_LEGISLATURE_URI)
        self.limit = _bounded_limit(limit if limit is not None else config.get("limit", 30))
        self.fetch_method = fetch_method or config.get("fetch_method", "auto")
        self.timeout = float(timeout if timeout is not None else config.get("timeout", 30))

    def fetch_documents(self) -> list[LegislativeDocument]:
        if not self.enabled:
            return []
        rows = sparql_query(
            self.endpoint_url,
            _build_camera_query(self.legislature_uri, self.limit),
            method=self.fetch_method,
            timeout=self.timeout,
        )
        fetched_at = datetime.now(UTC)
        return [_camera_row_to_document(row, fetched_at=fetched_at) for row in rows if row.get("title")]


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
