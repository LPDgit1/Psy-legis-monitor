"""Connector for Senato della Repubblica linked open data."""

from __future__ import annotations

from datetime import UTC, datetime

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.parsing import compact_identifier, infer_status, parse_connector_date
from app.connectors.sparql import sparql_query
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import normalize_text


SENATO_ENDPOINT = "https://dati.senato.it/sparql"


class SenatoConnector(BaseConnector):
    """Fetch recent Senate bill phases from dati.senato.it."""

    name = "senato"

    def __init__(
        self,
        *,
        endpoint_url: str | None = None,
        legislature: int | None = None,
        limit: int | None = None,
        fetch_method: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        config = load_yaml(settings.sources_path).get("senato", {})
        self.enabled = config.get("enabled", True) if enabled is None else enabled
        self.endpoint_url = endpoint_url or config.get("endpoint_url", SENATO_ENDPOINT)
        self.legislature = int(legislature if legislature is not None else config.get("legislature", 19))
        self.limit = _bounded_limit(limit if limit is not None else config.get("limit", 30))
        self.fetch_method = fetch_method or config.get("fetch_method", "auto")
        self.timeout = float(timeout if timeout is not None else config.get("timeout", 30))

    def fetch_documents(self) -> list[LegislativeDocument]:
        if not self.enabled:
            return []
        rows = sparql_query(
            self.endpoint_url,
            _build_senato_query(self.legislature, self.limit),
            method=self.fetch_method,
            timeout=self.timeout,
        )
        fetched_at = datetime.now(UTC)
        return [
            _senato_row_to_document(row, fetched_at=fetched_at, legislature=self.legislature)
            for row in rows
            if row.get("titolo")
        ]


def _build_senato_query(legislature: int, limit: int) -> str:
    return f"""
PREFIX osr: <http://dati.senato.it/osr/>

SELECT DISTINCT ?ddl ?idFase ?ramo ?legislatura ?numeroFase ?titolo ?titoloBreve
                ?natura ?stato ?dataStato ?dataPresentazione
                ?presentatoTrasmesso ?testoPresentato ?testoApprovato WHERE {{
  ?ddl a osr:Ddl.
  ?ddl osr:idFase ?idFase.
  ?ddl osr:statoDdl ?stato.
  ?ddl osr:ramo ?ramo.
  ?ddl osr:dataPresentazione ?dataPresentazione.
  ?ddl osr:titolo ?titolo.
  OPTIONAL {{ ?ddl osr:titoloBreve ?titoloBreve }}
  ?ddl osr:presentatoTrasmesso ?presentatoTrasmesso.
  ?ddl osr:natura ?natura.
  ?ddl osr:dataStatoDdl ?dataStato.
  ?ddl osr:numeroFase ?numeroFase.
  ?ddl osr:legislatura ?legislatura.
  ?ddl osr:legislatura {legislature}.
  OPTIONAL {{ ?ddl osr:testoPresentato ?testoPresentato }}
  OPTIONAL {{ ?ddl osr:testoApprovato ?testoApprovato }}
}}
ORDER BY DESC(?dataPresentazione)
LIMIT {limit}
""".strip()


def _senato_row_to_document(
    row: dict[str, str],
    *,
    fetched_at: datetime,
    legislature: int,
) -> LegislativeDocument:
    title = normalize_text(row["titolo"])
    short_title = normalize_text(row.get("titoloBreve"))
    identifier = _senato_identifier(row)
    status_text = " ".join(part for part in [row.get("stato"), row.get("presentatoTrasmesso")] if part)
    public_url = _senato_public_url(row.get("idFase"), legislature)
    text = "\n\n".join(
        part
        for part in [
            title,
            short_title,
            f"Stato: {row.get('stato')}" if row.get("stato") else None,
            f"Natura: {row.get('natura')}" if row.get("natura") else None,
            f"Presentazione: {row.get('dataPresentazione')}" if row.get("dataPresentazione") else None,
            f"Ultimo stato: {row.get('dataStato')}" if row.get("dataStato") else None,
        ]
        if part
    )
    return LegislativeDocument(
        source="Senato della Repubblica - dati.senato.it",
        source_type="official_api",
        level="nazionale",
        act_type="disegno_di_legge",
        identifier=identifier,
        title=title,
        summary=short_title or None,
        date_presented=parse_connector_date(row.get("dataPresentazione")),
        last_update=fetched_at,
        status=infer_status(status_text, default="sconosciuto"),
        url=public_url or row.get("ddl"),
        text=text,
        metadata={
            "connector": SenatoConnector.name,
            "linked_data_url": row.get("ddl"),
            "id_fase": row.get("idFase"),
            "ramo": row.get("ramo"),
            "legislature": row.get("legislatura"),
            "data_stato": row.get("dataStato"),
            "natura": row.get("natura"),
            "testo_presentato": row.get("testoPresentato"),
            "testo_approvato": row.get("testoApprovato"),
            "accessed_at": fetched_at.isoformat(),
        },
    )


def _senato_identifier(row: dict[str, str]) -> str | None:
    ramo = normalize_text(row.get("ramo")).upper()
    numero = normalize_text(row.get("numeroFase"))
    if ramo and numero:
        return compact_identifier(f"{ramo}.{numero}")
    return compact_identifier(row.get("idFase") or row.get("ddl"))


def _senato_public_url(id_fase: str | None, legislature: int) -> str | None:
    if not id_fase:
        return None
    return f"https://www.senato.it/leg/{legislature}/BGT/Schede/Ddliter/{id_fase}.htm"


def _bounded_limit(value: object) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 30
    return max(1, min(limit, 200))
