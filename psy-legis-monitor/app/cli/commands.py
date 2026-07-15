"""CLI commands for the MVP."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from app.config.settings import load_yaml, settings
from app.connectors.gazzetta import GazzettaConnector
from app.connectors.mock import MockConnector
from app.core import models
from app.core.database import SessionLocal, init_db
from app.core.schemas import LegislativeDocument
from app.core.scoring import score_document
from app.core.taxonomy import classify_taxonomy
from app.services.alerting import build_alert
from app.services.export import export_markdown_report
from app.services.ingest import ingest_documents
from app.services.reports import generate_weekly_report


def cmd_ingest_mock(_: argparse.Namespace) -> None:
    init_db()
    documents = MockConnector().fetch_documents()
    with SessionLocal() as session:
        summary = ingest_documents(session, documents)
    print(
        f"Ingest mock completato: {summary.created} nuovi, "
        f"{summary.updated} aggiornati, {summary.alerts} alert."
    )


def cmd_ingest_rss(_: argparse.Namespace) -> None:
    from app.connectors.rss import RSSConnector

    init_db()
    documents = RSSConnector().fetch_documents()
    with SessionLocal() as session:
        summary = ingest_documents(session, documents)
    print(
        f"Ingest RSS completato: {summary.created} nuovi, "
        f"{summary.updated} aggiornati, {summary.alerts} alert."
    )


def cmd_ingest_pages(_: argparse.Namespace) -> None:
    from app.connectors.page import PageConnector

    init_db()
    documents = PageConnector().fetch_documents()
    with SessionLocal() as session:
        summary = ingest_documents(session, documents)
    print(
        f"Ingest pagine istituzionali completato: {summary.created} nuovi, "
        f"{summary.updated} aggiornati, {summary.alerts} alert."
    )


def cmd_ingest_camera(_: argparse.Namespace) -> None:
    from app.connectors.camera import CameraConnector

    _ingest_connector("Camera", CameraConnector().fetch_documents())


def cmd_update_camera_snapshot(args: argparse.Namespace) -> None:
    from app.connectors.camera import CameraConnector

    connector = CameraConnector(prefer_snapshot=False, live_fallback_enabled=False)
    payload = connector.update_snapshot(args.output)
    print(
        json.dumps(
            {
                "status": "ok",
                "snapshot": str(connector.snapshot_path if args.output is None else args.output),
                "generated_at": payload["generated_at"],
                "result_count": payload["result_count"],
                "newest_identifier": payload["newest_identifier"],
                "newest_date": payload["newest_date"],
            },
            ensure_ascii=False,
        )
    )


def cmd_ingest_senato(_: argparse.Namespace) -> None:
    from app.connectors.senato import SenatoConnector

    _ingest_connector("Senato", SenatoConnector().fetch_documents())


def cmd_ingest_normattiva(_: argparse.Namespace) -> None:
    from app.connectors.normattiva import NormattivaConnector

    _ingest_connector("Normattiva", NormattivaConnector().fetch_documents())


def cmd_ingest_ministero_salute(_: argparse.Namespace) -> None:
    from app.connectors.ministero_salute import MinisteroSaluteConnector

    _ingest_connector("Ministero Salute", MinisteroSaluteConnector().fetch_documents())


def cmd_ingest_agenas(_: argparse.Namespace) -> None:
    from app.connectors.agenas import AgenasConnector

    _ingest_connector("AGENAS", AgenasConnector().fetch_documents())


def cmd_ingest_eurlex(_: argparse.Namespace) -> None:
    from app.connectors.eurlex import EurLexConnector

    _ingest_connector("EUR-Lex", EurLexConnector().fetch_documents())


def cmd_ingest_regions(_: argparse.Namespace) -> None:
    _ingest_connector("Regioni prioritarie", _fetch_regions())


def cmd_ingest_priority(_: argparse.Namespace) -> None:
    init_db()
    documents = _fetch_priority_documents()
    with SessionLocal() as session:
        summary = ingest_documents(session, documents)
    print(
        f"Ingest fonti prioritarie completato: {summary.created} nuovi, "
        f"{summary.updated} aggiornati, {summary.alerts} alert "
        f"su {summary.seen} documenti letti."
    )


def cmd_purge_mock(_: argparse.Namespace) -> None:
    init_db()
    with SessionLocal() as session:
        documents = session.execute(select(models.Document)).scalars().all()
        mock_documents = [
            document
            for document in documents
            if document.source_type == "mock" or "mock" in document.source.lower()
        ]
        for document in mock_documents:
            session.delete(document)
        session.commit()
    print(f"Pulizia mock completata: rimossi {len(mock_documents)} documenti mock.")


def cmd_verify_connectors(_: argparse.Namespace) -> None:
    checks = [
        ("Gazzetta Ufficiale", _fetch_gazzetta),
        ("Camera", _fetch_camera),
        ("Senato", _fetch_senato),
        ("Normattiva", _fetch_normattiva),
        ("Ministero Salute", _fetch_ministero_salute),
        ("AGENAS", _fetch_agenas),
        ("EUR-Lex", _fetch_eurlex),
        ("Regione Veneto", _fetch_veneto),
        ("Regione Lombardia", _fetch_lombardia),
        ("RSS CNOP/ENPAP", _fetch_rss),
        ("Pagine istituzionali", _fetch_pages),
    ]
    failures = 0
    for label, fetcher in checks:
        try:
            documents = fetcher()
        except Exception as exc:
            failures += 1
            print(f"ERRORE {label}: {exc}")
            continue
        source_counts = Counter(document.source for document in documents)
        sources = "; ".join(f"{source}: {count}" for source, count in source_counts.most_common())
        print(f"OK {label}: {len(documents)} documenti" + (f" ({sources})" if sources else ""))
    if failures:
        print(f"Verifica completata con {failures} fonti in errore.")
    else:
        print("Verifica completata senza errori.")


def cmd_ingest_gazzetta(args: argparse.Namespace) -> None:
    init_db()
    config = load_yaml(settings.sources_path).get("gazzetta", {})
    connector = GazzettaConnector(
        fetch_act_text=args.fetch_act_text or bool(config.get("fetch_act_text", False)),
        fetch_method=config.get("fetch_method", "auto"),
    )
    if args.max_issues is not None:
        connector.series = [
            series.__class__(
                name=series.name,
                list_url=series.list_url,
                source=series.source,
                level=series.level,
                region=series.region,
                max_issues=args.max_issues,
            )
            for series in connector.series
        ]
    documents = connector.fetch_documents()
    with SessionLocal() as session:
        summary = ingest_documents(session, documents)
    print(
        f"Ingest Gazzetta completato: {summary.created} nuovi, "
        f"{summary.updated} aggiornati, {summary.alerts} alert "
        f"su {summary.seen} documenti letti."
    )


def cmd_ingest_all(args: argparse.Namespace) -> None:
    init_db()
    config = load_yaml(settings.sources_path).get("gazzetta", {})
    documents = []
    if args.include_mock:
        documents.extend(MockConnector().fetch_documents())
    documents.extend(
        GazzettaConnector(
            fetch_act_text=args.fetch_act_text or bool(config.get("fetch_act_text", False)),
            fetch_method=config.get("fetch_method", "auto"),
        ).fetch_documents()
    )
    try:
        from app.connectors.rss import RSSConnector

        documents.extend(RSSConnector().fetch_documents())
    except Exception as exc:
        print(f"Ingest RSS saltato: {exc}")
    try:
        from app.connectors.page import PageConnector

        documents.extend(PageConnector().fetch_documents())
    except Exception as exc:
        print(f"Ingest pagine istituzionali saltato: {exc}")
    documents.extend(_fetch_priority_documents())
    with SessionLocal() as session:
        summary = ingest_documents(session, documents)
    print(
        f"Ingest completo: {summary.created} nuovi, {summary.updated} aggiornati, "
        f"{summary.alerts} alert su {summary.seen} documenti letti."
    )


def _ingest_connector(label: str, documents: list[LegislativeDocument]) -> None:
    init_db()
    with SessionLocal() as session:
        summary = ingest_documents(session, documents)
    print(
        f"Ingest {label} completato: {summary.created} nuovi, "
        f"{summary.updated} aggiornati, {summary.alerts} alert "
        f"su {summary.seen} documenti letti."
    )


def _fetch_priority_documents() -> list[LegislativeDocument]:
    documents: list[LegislativeDocument] = []
    _safe_extend(documents, "Camera", _fetch_camera)
    _safe_extend(documents, "Senato", _fetch_senato)
    _safe_extend(documents, "Normattiva", _fetch_normattiva)
    _safe_extend(documents, "Ministero Salute", _fetch_ministero_salute)
    _safe_extend(documents, "AGENAS", _fetch_agenas)
    _safe_extend(documents, "EUR-Lex", _fetch_eurlex)
    _safe_extend(documents, "Regione Veneto", _fetch_veneto)
    _safe_extend(documents, "Regione Lombardia", _fetch_lombardia)
    return documents


def _safe_extend(
    documents: list[LegislativeDocument],
    label: str,
    fetcher,
) -> None:
    try:
        documents.extend(fetcher())
    except Exception as exc:
        print(f"Ingest {label} saltato: {exc}")


def _fetch_camera() -> list[LegislativeDocument]:
    from app.connectors.camera import CameraConnector

    return CameraConnector().fetch_documents()


def _fetch_gazzetta() -> list[LegislativeDocument]:
    config = load_yaml(settings.sources_path).get("gazzetta", {})
    return GazzettaConnector(
        fetch_act_text=bool(config.get("fetch_act_text", False)),
        fetch_method=config.get("fetch_method", "auto"),
    ).fetch_documents()


def _fetch_rss() -> list[LegislativeDocument]:
    from app.connectors.rss import RSSConnector

    return RSSConnector().fetch_documents()


def _fetch_pages() -> list[LegislativeDocument]:
    from app.connectors.page import PageConnector

    return PageConnector().fetch_documents()


def _fetch_senato() -> list[LegislativeDocument]:
    from app.connectors.senato import SenatoConnector

    return SenatoConnector().fetch_documents()


def _fetch_normattiva() -> list[LegislativeDocument]:
    from app.connectors.normattiva import NormattivaConnector

    return NormattivaConnector().fetch_documents()


def _fetch_ministero_salute() -> list[LegislativeDocument]:
    from app.connectors.ministero_salute import MinisteroSaluteConnector

    return MinisteroSaluteConnector().fetch_documents()


def _fetch_agenas() -> list[LegislativeDocument]:
    from app.connectors.agenas import AgenasConnector

    return AgenasConnector().fetch_documents()


def _fetch_eurlex() -> list[LegislativeDocument]:
    from app.connectors.eurlex import EurLexConnector

    return EurLexConnector().fetch_documents()


def _fetch_regions() -> list[LegislativeDocument]:
    documents: list[LegislativeDocument] = []
    _safe_extend(documents, "Regione Veneto", _fetch_veneto)
    _safe_extend(documents, "Regione Lombardia", _fetch_lombardia)
    return documents


def _fetch_veneto() -> list[LegislativeDocument]:
    from app.connectors.regions.veneto import VenetoConnector

    return VenetoConnector().fetch_documents()


def _fetch_lombardia() -> list[LegislativeDocument]:
    from app.connectors.regions.lombardia import LombardiaConnector

    return LombardiaConnector().fetch_documents()


def _schema_from_document(document: models.Document) -> LegislativeDocument:
    return LegislativeDocument(
        source=document.source,
        source_type=document.source_type,
        level=document.level,
        region=document.region,
        act_type=document.act_type,
        identifier=document.identifier,
        title=document.title,
        summary=document.summary,
        date_presented=document.date_presented,
        date_published=document.date_published,
        last_update=document.last_update,
        status=document.status,
        url=document.url,
        text=document.text,
        metadata=document.metadata_json or {},
    )


def cmd_score_all(_: argparse.Namespace) -> None:
    init_db()
    with SessionLocal() as session:
        documents = session.execute(select(models.Document)).scalars().all()
        for orm_document in documents:
            document = _schema_from_document(orm_document)
            score = score_document(document)
            taxonomy = classify_taxonomy(document)
            session.add(
                models.RelevanceAssessment(
                    document_id=orm_document.id,
                    score=score.total_score,
                    relevance_class=score.relevance_class,
                    category_scores=score.category_scores,
                    found_terms=score.found_terms,
                    domains=taxonomy.domains,
                    method="keyword_rules",
                    explanation="Ricalcolo manuale da CLI.",
                )
            )
            alert = build_alert(document, score, taxonomy)
            if alert:
                session.add(
                    models.Alert(
                        document_id=orm_document.id,
                        level=alert.level,
                        reason=alert.reason,
                        domains=alert.domains,
                        recommended_action=alert.recommended_action,
                        status=alert.status,
                    )
                )
        session.commit()
    print(f"Ricalcolo completato per {len(documents)} documenti.")


def cmd_generate_report(args: argparse.Namespace) -> None:
    init_db()
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=7)
    with SessionLocal() as session:
        documents = session.execute(select(models.Document)).scalars().all()
        orm_alerts = session.execute(select(models.Alert)).scalars().all()
        alerts = []
        by_id = {document.id: document for document in documents}
        for alert in orm_alerts:
            document = by_id.get(alert.document_id)
            alerts.append(
                {
                    "title": document.title if document else f"Alert {alert.id}",
                    "source": document.source if document else "",
                    "status": document.status if document else "",
                    "url": document.url if document else "",
                    "level": alert.level,
                    "reason": alert.reason,
                    "recommended_action": alert.recommended_action,
                }
            )
        markdown = generate_weekly_report(
            documents,
            alerts=alerts,
            period_start=start,
            period_end=end,
        )
        output = export_markdown_report(markdown, args.output)
    print(f"Report generato: {output}")


def cmd_run_dashboard(args: argparse.Namespace) -> None:
    target = Path(__file__).resolve().parents[1] / "ui" / "streamlit_app.py"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(target),
        "--global.developmentMode=false",
        "--browser.gatherUsageStats=false",
    ]
    if args.port:
        command.extend(["--server.port", str(args.port)])
    subprocess.run(command, check=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="psy-legis",
        description="MVP di legislative intelligence per atti rilevanti per la psicologia.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_mock = subparsers.add_parser("ingest-mock")
    ingest_mock.set_defaults(func=cmd_ingest_mock)

    ingest_rss = subparsers.add_parser("ingest-rss")
    ingest_rss.set_defaults(func=cmd_ingest_rss)

    ingest_pages = subparsers.add_parser("ingest-pages")
    ingest_pages.set_defaults(func=cmd_ingest_pages)

    ingest_camera = subparsers.add_parser("ingest-camera")
    ingest_camera.set_defaults(func=cmd_ingest_camera)

    update_camera_snapshot = subparsers.add_parser("update-camera-snapshot")
    update_camera_snapshot.add_argument("--output")
    update_camera_snapshot.set_defaults(func=cmd_update_camera_snapshot)

    ingest_senato = subparsers.add_parser("ingest-senato")
    ingest_senato.set_defaults(func=cmd_ingest_senato)

    ingest_normattiva = subparsers.add_parser("ingest-normattiva")
    ingest_normattiva.set_defaults(func=cmd_ingest_normattiva)

    ingest_ministero_salute = subparsers.add_parser("ingest-ministero-salute")
    ingest_ministero_salute.set_defaults(func=cmd_ingest_ministero_salute)

    ingest_agenas = subparsers.add_parser("ingest-agenas")
    ingest_agenas.set_defaults(func=cmd_ingest_agenas)

    ingest_eurlex = subparsers.add_parser("ingest-eurlex")
    ingest_eurlex.set_defaults(func=cmd_ingest_eurlex)

    ingest_regions = subparsers.add_parser("ingest-regions")
    ingest_regions.set_defaults(func=cmd_ingest_regions)

    ingest_priority = subparsers.add_parser("ingest-priority")
    ingest_priority.set_defaults(func=cmd_ingest_priority)

    purge_mock = subparsers.add_parser("purge-mock")
    purge_mock.set_defaults(func=cmd_purge_mock)

    verify_connectors = subparsers.add_parser("verify-connectors")
    verify_connectors.set_defaults(func=cmd_verify_connectors)

    ingest_gazzetta = subparsers.add_parser("ingest-gazzetta")
    ingest_gazzetta.add_argument("--fetch-act-text", action="store_true")
    ingest_gazzetta.add_argument("--max-issues", type=int)
    ingest_gazzetta.set_defaults(func=cmd_ingest_gazzetta)

    ingest_all = subparsers.add_parser("ingest-all")
    ingest_all.add_argument("--include-mock", action="store_true")
    ingest_all.add_argument("--fetch-act-text", action="store_true")
    ingest_all.set_defaults(func=cmd_ingest_all)

    score_all = subparsers.add_parser("score-all")
    score_all.set_defaults(func=cmd_score_all)

    report = subparsers.add_parser("generate-report")
    report.add_argument("--output", default="reports/weekly_report.md")
    report.add_argument("--start")
    report.add_argument("--end")
    report.set_defaults(func=cmd_generate_report)

    dashboard = subparsers.add_parser("run-dashboard")
    dashboard.add_argument("--port", type=int)
    dashboard.set_defaults(func=cmd_run_dashboard)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
