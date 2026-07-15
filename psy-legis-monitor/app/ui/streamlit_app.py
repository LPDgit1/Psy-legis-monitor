"""Streamlit dashboard for legislative intelligence triage."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import escape, unescape

import streamlit as st
from sqlalchemy import select

from app.config.settings import load_yaml, settings
from app.core import models
from app.core.database import SessionLocal, init_db
from app.services.export import export_markdown_report
from app.services.ingest import ingest_documents
from app.services.reports import generate_weekly_report
from app.ui.document_view import (
    act_type_label,
    bucket_label,
    clean_display_text,
    display_region,
    document_bucket,
    document_type_label,
    is_mock_row,
    is_potential_primary_document,
    is_primary_document,
    is_relevant_primary_document,
    level_label,
    sort_date_value,
    status_label,
)


try:
    from app.ui.document_view import is_excluded_noise_document
except ImportError:
    def is_excluded_noise_document(row: dict) -> bool:
        text = " ".join(
            str(row.get(key) or "").lower()
            for key in ["title", "summary", "text", "source"]
        )
        noise = [
            "peste suina",
            "cinghial",
            "carcasse",
            "veterinar",
            "fauna selvatica",
            "sanita animale",
            "frati minori",
            "ordine dei frati",
            "fitoterap",
            "prodotti fitosanitari",
        ]
        direct = ["psicolog", "psicoterap", "salute mentale", "enpap", "cnop"]
        return any(term in text for term in noise) and not any(term in text for term in direct)


st.set_page_config(page_title="psy-legis-monitor", layout="wide")

if "connector_issues" not in st.session_state:
    st.session_state["connector_issues"] = []


@st.cache_data(ttl=30)
def load_data() -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    init_db()
    with SessionLocal() as session:
        documents = session.execute(select(models.Document)).scalars().all()
        assessments = session.execute(select(models.RelevanceAssessment)).scalars().all()
        events = session.execute(select(models.LegislativeEvent)).scalars().all()
        alerts = session.execute(select(models.Alert)).scalars().all()
        versions = session.execute(select(models.DocumentVersion)).scalars().all()

    document_rows = [
        {
            "id": document.id,
            "document_key": document.document_key,
            "title": clean_display_text(document.title),
            "summary": clean_display_text(document.summary),
            "source": clean_display_text(document.source),
            "source_type": document.source_type,
            "level": document.level,
            "region": clean_display_text(document.region) if document.region else "",
            "act_type": document.act_type,
            "status": document.status,
            "date_presented": document.date_presented,
            "date_published": document.date_published,
            "primary_date": document.date_published or document.date_presented,
            "last_update": document.last_update,
            "url": document.url or "",
            "text": clean_display_text(document.text),
            "metadata": document.metadata_json or {},
        }
        for document in documents
    ]
    assessment_rows = [
        {
            "document_id": assessment.document_id,
            "score": assessment.score,
            "relevance_class": assessment.relevance_class,
            "found_terms": assessment.found_terms or {},
            "domains": assessment.domains or [],
            "method": assessment.method,
            "explanation": assessment.explanation or "",
            "created_at": assessment.created_at,
        }
        for assessment in assessments
    ]
    event_rows = [
        {
            "document_id": event.document_id,
            "event_type": event.event_type,
            "summary": event.summary,
            "created_at": event.created_at,
            "before": event.before_json or {},
            "after": event.after_json or {},
        }
        for event in events
    ]
    alert_rows = [
        {
            "document_id": alert.document_id,
            "level": alert.level,
            "reason": alert.reason,
            "domains": alert.domains or [],
            "recommended_action": alert.recommended_action,
            "status": alert.status,
            "generated_at": alert.generated_at,
        }
        for alert in alerts
    ]
    version_rows = [
        {
            "document_id": version.document_id,
            "version_number": version.version_number,
            "text_hash": version.text_hash,
            "created_at": version.created_at,
            "source_last_update": version.source_last_update,
        }
        for version in versions
    ]
    return document_rows, assessment_rows, event_rows, alert_rows, version_rows


def latest_by_document(rows: list[dict], date_key: str) -> dict[int, dict]:
    latest: dict[int, dict] = {}
    for row in sorted(rows, key=lambda item: item.get(date_key) or datetime.min):
        latest[row["document_id"]] = row
    return latest


def rows_by_document(rows: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["document_id"]].append(row)
    return grouped


def refresh_data() -> None:
    st.session_state["connector_issues"] = []
    load_data.clear()
    st.rerun()


def register_connector_issue(connector_name: str, exc: Exception) -> None:
    issue = {
        "connector": connector_name,
        "message": compact_connector_error(connector_name, exc),
    }
    st.session_state.setdefault("connector_issues", []).append(issue)


def render_connector_issues() -> None:
    issues = st.session_state.get("connector_issues", [])
    if not issues:
        return
    names = ", ".join(sorted({clean_display_text(issue["connector"]) for issue in issues}))
    st.caption(f"Fonti non aggiornate nell'ultima esecuzione: {names}.")


def ingest_with_connector(connector_name: str) -> None:
    init_db()
    st.session_state["connector_issues"] = []
    if connector_name == "gazzetta":
        from app.connectors.gazzetta import GazzettaConnector

        documents = GazzettaConnector().fetch_documents()
    elif connector_name == "rss":
        from app.connectors.rss import RSSConnector

        documents = RSSConnector().fetch_documents()
    elif connector_name == "pages":
        from app.connectors.page import PageConnector

        documents = PageConnector().fetch_documents()
    elif connector_name == "camera":
        from app.connectors.camera import CameraConnector

        documents = CameraConnector().fetch_documents()
    elif connector_name == "senato":
        from app.connectors.senato import SenatoConnector

        documents = SenatoConnector().fetch_documents()
    elif connector_name == "normattiva":
        from app.connectors.normattiva import NormattivaConnector

        documents = NormattivaConnector().fetch_documents()
    elif connector_name == "priority":
        documents = _fetch_priority_documents()
    elif connector_name == "normative":
        documents = _fetch_normative_documents()
    elif connector_name == "institutional":
        documents = _fetch_institutional_documents()
    else:
        raise ValueError(f"Connettore non supportato: {connector_name}")
    with SessionLocal() as session:
        summary = ingest_documents(session, documents)
    st.success(
        f"Ingest completato: {summary.created} nuovi, {summary.updated} aggiornati, "
        f"{summary.alerts} alert."
    )
    refresh_data()


def _fetch_priority_documents() -> list:
    documents = []
    documents.extend(_fetch_normative_documents())
    documents.extend(_fetch_institutional_documents())
    return documents


def _fetch_normative_documents() -> list:
    documents = []
    from app.connectors.eurlex import EurLexConnector
    from app.connectors.gazzetta import GazzettaConnector
    from app.connectors.ministero_salute import MinisteroSaluteConnector
    from app.connectors.normattiva import NormattivaConnector
    from app.connectors.regions.lombardia import LombardiaConnector
    from app.connectors.regions.veneto import VenetoConnector
    from app.connectors.senato import SenatoConnector

    connectors = [
        GazzettaConnector(),
        SenatoConnector(),
        NormattivaConnector(),
        MinisteroSaluteConnector(),
        EurLexConnector(),
        VenetoConnector(),
        LombardiaConnector(),
    ]
    if camera_auto_update_enabled():
        from app.connectors.camera import CameraConnector

        connectors.insert(1, CameraConnector())

    for connector in connectors:
        try:
            documents.extend(connector.fetch_documents())
        except Exception as exc:
            show_connector_warning(connector.name, exc)
    return documents


def _fetch_institutional_documents() -> list:
    documents = []
    from app.connectors.agenas import AgenasConnector
    from app.connectors.page import PageConnector
    from app.connectors.rss import RSSConnector

    for connector in [RSSConnector(), PageConnector(), AgenasConnector()]:
        try:
            documents.extend(connector.fetch_documents())
        except Exception as exc:
            show_connector_warning(connector.name, exc)
    return documents


def _fetch_individual_documents(connector_name: str) -> list:
    if connector_name == "gazzetta":
        from app.connectors.gazzetta import GazzettaConnector

        return GazzettaConnector().fetch_documents()
    if connector_name == "rss":
        from app.connectors.rss import RSSConnector

        return RSSConnector().fetch_documents()
    if connector_name == "pages":
        from app.connectors.page import PageConnector

        return PageConnector().fetch_documents()
    if connector_name == "camera":
        from app.connectors.camera import CameraConnector

        return CameraConnector().fetch_documents()
    if connector_name == "senato":
        from app.connectors.senato import SenatoConnector

        return SenatoConnector().fetch_documents()
    if connector_name == "normattiva":
        from app.connectors.normattiva import NormattivaConnector

        return NormattivaConnector().fetch_documents()
    if connector_name == "ministero_salute":
        from app.connectors.ministero_salute import MinisteroSaluteConnector

        return MinisteroSaluteConnector().fetch_documents()
    if connector_name == "agenas":
        from app.connectors.agenas import AgenasConnector

        return AgenasConnector().fetch_documents()
    if connector_name == "eurlex":
        from app.connectors.eurlex import EurLexConnector

        return EurLexConnector().fetch_documents()
    if connector_name == "veneto":
        from app.connectors.regions.veneto import VenetoConnector

        return VenetoConnector().fetch_documents()
    if connector_name == "lombardia":
        from app.connectors.regions.lombardia import LombardiaConnector

        return LombardiaConnector().fetch_documents()
    raise ValueError(f"Connettore non supportato: {connector_name}")


def ingest_individual(connector_name: str, label: str) -> None:
    try:
        init_db()
        st.session_state["connector_issues"] = []
        documents = _fetch_individual_documents(connector_name)
        with SessionLocal() as session:
            summary = ingest_documents(session, documents)
        st.success(
            f"{label}: {summary.created} nuovi, {summary.updated} aggiornati, "
            f"{summary.alerts} alert."
        )
        refresh_data()
    except Exception as exc:
        st.error(f"{label} non riuscito: {compact_connector_error(connector_name, exc)}")


def _legacy_priority_fetch() -> list:
    """Kept only to avoid stale Streamlit sessions failing during hot reload."""
    documents = []
    try:
        from app.connectors.agenas import AgenasConnector
        from app.connectors.eurlex import EurLexConnector
        from app.connectors.ministero_salute import MinisteroSaluteConnector
        from app.connectors.normattiva import NormattivaConnector
        from app.connectors.regions.lombardia import LombardiaConnector
        from app.connectors.regions.veneto import VenetoConnector
        from app.connectors.senato import SenatoConnector

        documents = []
        connectors = [
            SenatoConnector(),
            NormattivaConnector(),
            MinisteroSaluteConnector(),
            AgenasConnector(),
            EurLexConnector(),
            VenetoConnector(),
            LombardiaConnector(),
        ]
        if camera_auto_update_enabled():
            from app.connectors.camera import CameraConnector

            connectors.insert(0, CameraConnector())
        for connector in connectors:
            try:
                documents.extend(connector.fetch_documents())
            except Exception as exc:
                show_connector_warning(connector.name, exc)
    except Exception:
        return documents
    return documents


def counter_chart_rows(counter: Counter) -> list[dict]:
    return [
        {"Categoria": key or "non classificato", "Conteggio": value}
        for key, value in counter.items()
        if key
    ]


def show_connector_warning(connector_name: str, exc: Exception) -> None:
    register_connector_issue(connector_name, exc)


def compact_connector_error(connector_name: str, exc: Exception) -> str:
    text = clean_display_text(str(exc))
    if connector_name == "camera" and "Snapshot Camera" in text:
        return (
            "Snapshot Camera non ancora disponibile o non valida. "
            "Eseguire il workflow GitHub 'Aggiorna snapshot Camera'."
        )
    if connector_name == "camera" and "SPARQL" in text:
        return "Camera non aggiornata; l'ultima snapshot valida e stata conservata."
    return text[:240] + "..." if len(text) > 240 else text


def camera_auto_update_enabled() -> bool:
    camera_config = load_yaml(settings.sources_path).get("camera", {})
    return bool(camera_config.get("auto_update_enabled", False))


def render_camera_diagnostics(diagnostics: dict[str, object]) -> None:
    status = diagnostics.get("snapshot_status")
    if status == "ok":
        st.success(
            f"Snapshot Camera disponibile: {diagnostics.get('result_count', 0)} atti, "
            f"aggiornata il {diagnostics.get('generated_at', '')}."
        )
    elif status == "stale":
        st.warning(
            f"Snapshot Camera disponibile ma non recente: "
            f"{diagnostics.get('age_hours', 0)} ore. I dati restano consultabili."
        )
    else:
        message = clean_display_text(diagnostics.get("message"))
        st.warning(message or "Snapshot Camera non disponibile.")
    st.caption(
        "La Camera viene acquisita fuori dalla sessione Streamlit e letta "
        "dall'ultima snapshot valida."
    )


def render_table(rows: list[dict], *, max_rows: int = 100) -> None:
    if not rows:
        st.caption("Nessun dato")
        return
    visible_rows = rows[:max_rows]
    headers = list(visible_rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in visible_rows:
        values = [_format_cell(row.get(header)) for header in headers]
        lines.append("| " + " | ".join(values) + " |")
    st.markdown("\n".join(lines))
    if len(rows) > max_rows:
        st.caption(f"Mostrate {max_rows} righe su {len(rows)}.")


def render_document_table(rows: list[dict], *, max_rows: int = 120) -> None:
    if not rows:
        st.caption("Nessun dato")
        return
    visible_rows = rows[:max_rows]
    table_rows = "\n".join(_document_table_row(row) for row in visible_rows)
    table_html = f"""
<style>
.document-table-wrap {{
    max-height: 620px;
    overflow: auto;
    border: 1px solid rgba(49, 51, 63, 0.18);
    border-radius: 6px;
}}
.document-table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    font-size: 0.92rem;
}}
.document-table th {{
    position: sticky;
    top: 0;
    z-index: 1;
    background: rgb(250, 250, 250);
    border-bottom: 1px solid rgba(49, 51, 63, 0.2);
    color: rgb(49, 51, 63);
    font-weight: 600;
    padding: 0.45rem 0.55rem;
    text-align: left;
}}
.document-table td {{
    border-bottom: 1px solid rgba(49, 51, 63, 0.12);
    padding: 0.42rem 0.55rem;
    vertical-align: top;
}}
.document-table .date-cell {{
    width: 7.2rem;
    white-space: nowrap;
}}
.document-table .type-cell {{
    width: 7.4rem;
    white-space: nowrap;
}}
.document-table .title-cell {{
    width: auto;
    overflow-wrap: anywhere;
    line-height: 1.32;
}}
.document-table .link-cell {{
    width: 4.6rem;
    text-align: center;
    white-space: nowrap;
}}
</style>
<div class="document-table-wrap">
<table class="document-table">
<thead>
<tr>
<th class="date-cell">Data</th>
<th class="type-cell">Tipo</th>
<th class="title-cell">Titolo</th>
<th class="link-cell">Apri</th>
</tr>
</thead>
<tbody>
{table_rows}
</tbody>
</table>
</div>
""".strip()
    st.markdown(
        table_html,
        unsafe_allow_html=True,
    )
    if len(rows) > max_rows:
        st.caption(f"Mostrate {max_rows} righe su {len(rows)}.")


def _document_table_row(row: dict) -> str:
    raw_url = str(row.get("Apri") or "")
    link = (
        f'<a href="{escape(raw_url, quote=True)}" target="_blank" rel="noopener noreferrer">Apri</a>'
        if raw_url
        else ""
    )
    return (
        "<tr>"
        f'<td class="date-cell">{_escape_cell_text(_format_display_date(row.get("Data")))}</td>'
        f'<td class="type-cell">{_escape_cell_text(row.get("Tipo"))}</td>'
        f'<td class="title-cell">{_escape_cell_text(row.get("Titolo"))}</td>'
        f'<td class="link-cell">{link}</td>'
        "</tr>"
    )


def _escape_cell_text(value: object) -> str:
    text = clean_display_text(value)
    for _ in range(6):
        decoded = unescape(text)
        if decoded == text:
            break
        text = clean_display_text(decoded)
    return escape(text, quote=False)


def _format_display_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return clean_display_text(value)


def _format_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text[:140] + "..." if len(text) > 140 else text


def _format_option_label(row: dict) -> str:
    date_part = row["primary_date"].isoformat() if row.get("primary_date") else "senza data"
    title = clean_display_text(row["title"])
    if len(title) > 110:
        title = title[:107] + "..."
    return f"{date_part} | {row['document_type_label']} | {title}"


def compact_table_title(title: str, *, limit: int = 180) -> str:
    title = clean_display_text(title)
    return title[: limit - 3] + "..." if len(title) > limit else title


def compact_document_type_label(label: str) -> str:
    labels = {
        "Proposta di legge": "Proposta",
        "Disegno di legge": "DDL",
        "Legge regionale": "Legge reg.",
        "Regolamento regionale": "Reg. reg.",
        "Decreto regionale": "Decr. reg.",
        "Decreto-legge": "DL",
        "Decreto legislativo": "D.lgs.",
        "DGR / delibera regionale": "DGR",
        "Atto normativo": "Norma",
        "News / aggiornamento": "News",
    }
    return labels.get(label, label)


def render_counter(counter: Counter) -> None:
    rows = counter_chart_rows(counter)
    if not rows:
        st.caption("Nessun dato")
        return
    for row in rows:
        st.write(f"{row['Categoria']}: {row['Conteggio']}")


documents, assessments, events, alerts, versions = load_data()
latest_assessment_by_doc = latest_by_document(assessments, "created_at")
latest_alert_by_doc = latest_by_document(alerts, "generated_at")
events_by_doc = rows_by_document(events)
alerts_by_doc = rows_by_document(alerts)
versions_by_doc = rows_by_document(versions)

for row in documents:
    assessment = latest_assessment_by_doc.get(row["id"], {})
    alert = latest_alert_by_doc.get(row["id"], {})
    row["relevance_class"] = assessment.get("relevance_class", "")
    row["score"] = assessment.get("score", 0)
    row["domains_list"] = assessment.get("domains", [])
    row["domains"] = ", ".join(row["domains_list"])
    row["found_terms"] = assessment.get("found_terms", {})
    row["alert_level"] = alert.get("level", "")
    row["alert_status"] = alert.get("status", "")
    row["recommended_action"] = alert.get("recommended_action", "")
    row["bucket"] = document_bucket(row)
    row["bucket_label"] = bucket_label(row)
    row["act_type_label"] = act_type_label(row["act_type"])
    row["document_type_label"] = document_type_label(row)
    row["status_label"] = status_label(row["status"])
    row["level_label"] = level_label(row["level"])
    row["display_region"] = display_region(row)

documents = [row for row in documents if not is_mock_row(row)]


st.title("psy-legis-monitor")
render_connector_issues()

with st.sidebar:
    st.header("Aggiornamento dati")
    if st.button("Aggiorna atti normativi", type="primary", use_container_width=True):
        try:
            ingest_with_connector("normative")
        except Exception as exc:
            st.error(f"Aggiornamento atti normativi non riuscito: {exc}")
    col_refresh, col_all = st.columns(2)
    if col_refresh.button("Ricarica", use_container_width=True):
        refresh_data()
    if col_all.button("Tutto", use_container_width=True):
        try:
            ingest_with_connector("priority")
        except Exception as exc:
            st.error(f"Aggiornamento completo non riuscito: {exc}")
    if st.button("News / contesto", use_container_width=True):
        try:
            ingest_with_connector("institutional")
        except Exception as exc:
            st.error(f"Aggiornamento news non riuscito: {exc}")

    with st.expander("Fonti singole"):
        left_button, right_button = st.columns(2)
        if left_button.button("Gazzetta", use_container_width=True):
            ingest_individual("gazzetta", "Gazzetta")
        if right_button.button("Camera", use_container_width=True):
            ingest_individual("camera", "Camera")
        if st.button("Stato Camera", use_container_width=True):
            from app.connectors.camera import CameraConnector

            try:
                diagnostics = CameraConnector().diagnose_snapshot()
                render_camera_diagnostics(diagnostics)
            except Exception as exc:
                st.error(f"Stato Camera non disponibile: {compact_connector_error('camera', exc)}")
        left_button, right_button = st.columns(2)
        if left_button.button("Senato", use_container_width=True):
            ingest_individual("senato", "Senato")
        if right_button.button("Normattiva", use_container_width=True):
            ingest_individual("normattiva", "Normattiva")
        left_button, right_button = st.columns(2)
        if left_button.button("Ministero", use_container_width=True):
            ingest_individual("ministero_salute", "Ministero Salute")
        if right_button.button("EUR-Lex", use_container_width=True):
            ingest_individual("eurlex", "EUR-Lex")
        left_button, right_button = st.columns(2)
        if left_button.button("AGENAS", use_container_width=True):
            ingest_individual("agenas", "AGENAS")
        if right_button.button("Veneto", use_container_width=True):
            ingest_individual("veneto", "Regione Veneto")
        left_button, right_button = st.columns(2)
        if left_button.button("Lombardia", use_container_width=True):
            ingest_individual("lombardia", "Regione Lombardia")
        if right_button.button("RSS", use_container_width=True):
            ingest_individual("rss", "RSS")
        if st.button("Pagine istituzionali", use_container_width=True):
            ingest_individual("pages", "Pagine")

    st.header("Vista")
    view_mode = st.radio(
        "Documenti da mostrare",
        [
            "Atti di interesse + potenziali",
            "Solo atti di interesse",
            "Atti potenziali",
            "Tutti gli atti/proposte",
            "Solo news / aggiornamenti",
            "Tutto",
        ],
        index=0,
    )
    search = st.text_input("Cerca nella vista selezionata", "")

    primary_dates = [row["primary_date"] for row in documents if row["primary_date"]]
    if primary_dates:
        min_date = min(primary_dates)
        max_date = max(primary_dates)
    else:
        min_date = date.today() - timedelta(days=30)
        max_date = date.today()
    date_range = st.date_input("Data atto o pubblicazione", value=(min_date, max_date))

    with st.expander("Filtri avanzati"):
        show_noise_documents = st.checkbox("Mostra esclusi per rumore", value=False)
        source_filter = st.multiselect("Fonte", sorted({row["source"] for row in documents}))
        level_filter = st.multiselect("Livello", sorted({row["level"] for row in documents}))
        region_filter = st.multiselect("Regione", sorted({row["region"] for row in documents if row["region"]}))
        act_filter = st.multiselect(
            "Tipo atto",
            sorted({row["act_type"] for row in documents}),
            format_func=act_type_label,
        )
        status_filter = st.multiselect(
            "Stato",
            sorted({row["status"] for row in documents}),
            format_func=status_label,
        )
        all_domains = sorted({domain for row in documents for domain in row["domains_list"]})
        domain_filter = st.multiselect("Area tematica", all_domains)


excluded_noise_count = sum(1 for row in documents if is_excluded_noise_document(row))
visible_documents = documents if show_noise_documents else [
    row for row in documents if not is_excluded_noise_document(row)
]

filtered = visible_documents
if view_mode == "Atti di interesse + potenziali":
    filtered = [
        row
        for row in filtered
        if is_relevant_primary_document(row) or is_potential_primary_document(row)
    ]
elif view_mode == "Solo atti di interesse":
    filtered = [row for row in filtered if is_relevant_primary_document(row)]
elif view_mode == "Atti potenziali":
    filtered = [row for row in filtered if is_potential_primary_document(row)]
elif view_mode == "Tutti gli atti/proposte":
    filtered = [row for row in filtered if is_primary_document(row)]
elif view_mode == "Solo news / aggiornamenti":
    filtered = [row for row in filtered if not is_primary_document(row)]

for key, selected in [
    ("source", source_filter),
    ("level", level_filter),
    ("region", region_filter),
    ("act_type", act_filter),
    ("status", status_filter),
]:
    if selected:
        filtered = [row for row in filtered if row.get(key) in selected]

if domain_filter:
    filtered = [row for row in filtered if set(row["domains_list"]) & set(domain_filter)]
if search:
    folded = search.lower()
    filtered = [
        row
        for row in filtered
        if folded in row["title"].lower()
        or folded in row["source"].lower()
        or folded in row["text"].lower()
    ]
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = [
        row
        for row in filtered
        if not row["primary_date"] or start <= row["primary_date"] <= end
    ]

primary_documents = [row for row in visible_documents if is_primary_document(row)]
relevant_documents = [row for row in visible_documents if is_relevant_primary_document(row)]
potential_documents = [row for row in visible_documents if is_potential_primary_document(row)]
proposal_count = sum(1 for row in visible_documents if document_bucket(row) == "proposta_legge")
normative_count = sum(1 for row in visible_documents if document_bucket(row) == "atto_normativo")

metric_cols = st.columns(6)
metric_cols[0].metric("In vista", len(filtered))
metric_cols[1].metric("Atti interesse", len(relevant_documents))
metric_cols[2].metric("Potenziali", len(potential_documents))
metric_cols[3].metric("Proposte / DDL", proposal_count)
metric_cols[4].metric("Leggi / decreti", normative_count)
metric_cols[5].metric("Esclusi", excluded_noise_count)

st.subheader("Documenti")
sorted_rows = sorted(
    filtered,
    key=lambda item: (sort_date_value(item["primary_date"]), item["score"]),
    reverse=True,
)
display_rows = [
    {
        "Data": row["primary_date"],
        "Tipo": compact_document_type_label(row["document_type_label"]),
        "Titolo": compact_table_title(row["title"]),
        "Apri": row["url"],
    }
    for row in sorted_rows
]
render_document_table(display_rows, max_rows=160)

with st.expander("Composizione dei documenti"):
    st.write("Classi")
    render_counter(Counter(row["bucket_label"] for row in visible_documents))
    st.write("Inclusione")
    render_counter(
        Counter(
            "Atti di interesse"
            if is_relevant_primary_document(row)
            else "Atti potenziali"
            if is_potential_primary_document(row)
            else "Fuori vista predefinita"
            for row in primary_documents
        )
    )
    st.write("Tipi atto")
    render_counter(Counter(row["document_type_label"] for row in documents if row["document_type_label"]))

if filtered:
    options = {
        f"{row['id']}": row
        for row in sorted_rows
    }
    selected_key = st.selectbox(
        "Documento selezionato",
        list(options.keys()),
        format_func=lambda key: _format_option_label(options[key]),
    )
    selected = options[selected_key]
    selected_assessment = latest_assessment_by_doc.get(selected["id"], {})
    selected_alerts = alerts_by_doc.get(selected["id"], [])
    selected_events = events_by_doc.get(selected["id"], [])
    selected_versions = versions_by_doc.get(selected["id"], [])

    st.subheader(clean_display_text(selected["title"]))
    detail_cols = st.columns(5)
    detail_cols[0].metric("Tipo", selected["document_type_label"])
    detail_cols[1].metric("Ambito", selected["bucket_label"])
    detail_cols[2].metric("Stato", selected["status_label"])
    detail_cols[3].metric("Versioni", len(selected_versions))
    detail_cols[4].metric("Eventi", len(selected_events))

    tab_summary, tab_scoring, tab_events, tab_alerts, tab_text = st.tabs(
        ["Sintesi", "Rilevanza tecnica", "Eventi e versioni", "Alert", "Testo"]
    )

    with tab_summary:
        st.write("Fonte:", selected["source"])
        st.write("Livello:", selected["level_label"])
        st.write("Regione:", selected["display_region"] or "-")
        st.write("Tipo documento:", selected["document_type_label"])
        st.write("Stato:", selected["status_label"])
        st.write("Data presentazione:", selected["date_presented"] or "-")
        st.write("Data pubblicazione:", selected["date_published"] or "-")
        if selected["url"]:
            st.link_button("Apri fonte ufficiale", selected["url"])
        st.write("Aree tematiche:", selected["domains_list"])
        st.json(selected["metadata"])

    with tab_scoring:
        st.write("Questi valori sono ausili tecnici per ordinamento e alert, non una valutazione giuridica.")
        st.write("Score:", selected_assessment.get("score", 0))
        st.write("Classe rilevanza:", selected_assessment.get("relevance_class", ""))
        st.write("Alert:", selected["alert_level"] or "-")
        st.write("Metodo:", selected_assessment.get("method", ""))
        st.write("Spiegazione:", selected_assessment.get("explanation", ""))
        st.write("Parole/frasi trovate")
        st.json(selected["found_terms"])

    with tab_events:
        st.write("Versioni")
        render_table(selected_versions)
        st.write("Eventi")
        render_table(selected_events)

    with tab_alerts:
        render_table(selected_alerts)

    with tab_text:
        st.text_area("Testo normalizzato", selected["text"], height=360)
else:
    st.info("Nessun documento corrisponde ai filtri selezionati.")

st.subheader("Report")
period_end = st.date_input("Fine periodo", value=date.today(), key="report_end")
period_start = st.date_input(
    "Inizio periodo",
    value=date.today() - timedelta(days=7),
    key="report_start",
)
if st.button("Esporta report Markdown"):
    alert_payloads = []
    by_id = {row["id"]: row for row in documents}
    for alert in alerts:
        document = by_id.get(alert["document_id"], {})
        alert_payloads.append({**document, **alert})
    markdown = generate_weekly_report(
        filtered,
        alerts=alert_payloads,
        period_start=period_start,
        period_end=period_end,
    )
    output = export_markdown_report(markdown, "reports/weekly_report.md")
    st.success(f"Report esportato in {output}")
    st.download_button("Scarica Markdown", markdown, file_name="weekly_report.md")
