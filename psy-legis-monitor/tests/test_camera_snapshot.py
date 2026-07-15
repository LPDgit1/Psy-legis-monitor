from datetime import UTC, datetime, timedelta

import pytest

from app.connectors.camera import CameraConnector, _build_camera_query
from app.connectors.camera_snapshot import (
    CameraSnapshotError,
    camera_snapshot_status,
    load_camera_snapshot,
    write_camera_snapshot,
)


ROWS = [
    {
        "atto": "http://dati.camera.it/ocd/attocamera.rdf/ac19_3014",
        "title": 'LUPI: "Disposizioni sull&amp;rsquo;autonomia" (3014)',
        "date": "20260710",
        "identifier": "3014",
    },
    {
        "atto": "http://dati.camera.it/ocd/attocamera.rdf/ac19_3013",
        "title": "Disposizioni in materia di psicologia scolastica",
        "date": "20260709",
        "identifier": "3013",
    },
]


def test_camera_snapshot_round_trip_normalizes_and_sorts_rows(tmp_path):
    path = tmp_path / "camera.json"

    payload = write_camera_snapshot(
        reversed(ROWS),
        path,
        endpoint_url="https://dati.camera.it/sparql",
        legislature_uri="http://dati.camera.it/ocd/legislatura.rdf/repubblica_19",
        generated_at=datetime(2026, 7, 16, 8, 0, tzinfo=UTC),
    )
    loaded = load_camera_snapshot(path)

    assert payload["result_count"] == 2
    assert loaded["newest_identifier"] == "3014"
    assert loaded["rows"][0]["title"] == 'LUPI: "Disposizioni sull’autonomia" (3014)'
    assert loaded["generated_at"] == "2026-07-16T08:00:00Z"


def test_invalid_camera_snapshot_does_not_replace_last_known_good(tmp_path):
    path = tmp_path / "camera.json"
    write_camera_snapshot(
        ROWS,
        path,
        endpoint_url="https://dati.camera.it/sparql",
        legislature_uri="http://dati.camera.it/ocd/legislatura.rdf/repubblica_19",
    )
    previous = path.read_bytes()

    with pytest.raises(CameraSnapshotError, match="incompleta"):
        write_camera_snapshot(
            [{"atto": "http://example.test/atto"}],
            path,
            endpoint_url="https://dati.camera.it/sparql",
            legislature_uri="http://dati.camera.it/ocd/legislatura.rdf/repubblica_19",
        )

    assert path.read_bytes() == previous


def test_partial_camera_snapshot_does_not_replace_last_known_good(tmp_path):
    path = tmp_path / "camera.json"
    write_camera_snapshot(
        ROWS,
        path,
        endpoint_url="https://dati.camera.it/sparql",
        legislature_uri="http://dati.camera.it/ocd/legislatura.rdf/repubblica_19",
    )
    previous = path.read_bytes()

    with pytest.raises(CameraSnapshotError, match="perso troppe righe"):
        write_camera_snapshot(
            ROWS[:1],
            path,
            endpoint_url="https://dati.camera.it/sparql",
            legislature_uri="http://dati.camera.it/ocd/legislatura.rdf/repubblica_19",
        )

    assert path.read_bytes() == previous


def test_camera_snapshot_status_reports_stale_data(tmp_path):
    path = tmp_path / "camera.json"
    write_camera_snapshot(
        ROWS,
        path,
        endpoint_url="https://dati.camera.it/sparql",
        legislature_uri="http://dati.camera.it/ocd/legislatura.rdf/repubblica_19",
        generated_at=datetime.now(UTC) - timedelta(hours=72),
    )

    status = camera_snapshot_status(path, max_age_hours=48)

    assert status["snapshot_status"] == "stale"
    assert status["result_count"] == 2


def test_camera_connector_reads_snapshot_without_network(monkeypatch, tmp_path):
    path = tmp_path / "camera.json"
    write_camera_snapshot(
        ROWS,
        path,
        endpoint_url="https://dati.camera.it/sparql",
        legislature_uri="http://dati.camera.it/ocd/legislatura.rdf/repubblica_19",
    )

    def fail_network(*args, **kwargs):
        raise AssertionError("The snapshot read path must not contact SPARQL")

    monkeypatch.setattr("app.connectors.camera.sparql_post_json", fail_network)
    documents = CameraConnector(snapshot_path=path).fetch_documents()

    assert [document.identifier for document in documents] == ["3014", "3013"]
    assert documents[0].url == "https://www.camera.it/leg19/126?leg=19&idDocumento=3014"
    assert documents[0].title == 'LUPI: "Disposizioni sull’autonomia" (3014)'
    assert "accessed_at" not in documents[0].metadata


def test_camera_snapshot_update_uses_row_stable_query(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_post(endpoint_url: str, query: str, *, timeout: float):
        captured.update(endpoint_url=endpoint_url, query=query, timeout=timeout)
        return ROWS

    monkeypatch.setattr("app.connectors.camera.sparql_post_json", fake_post)
    connector = CameraConnector(
        snapshot_path=tmp_path / "camera.json",
        prefer_snapshot=False,
        snapshot_minimum_result_count=1,
        live_retry_attempts=3,
    )

    payload = connector.update_snapshot()

    assert payload["result_count"] == 2
    assert "dc:creator" not in captured["query"]
    assert "dc:description" not in captured["query"]
    assert "isReferencedBy" not in captured["query"]
    assert "LIMIT 200" in captured["query"]


def test_camera_html_response_stops_without_retry(monkeypatch):
    calls = 0

    def blocked_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("POST SPARQL non ha restituito JSON valido. Risposta SPARQL in HTML")

    monkeypatch.setattr("app.connectors.camera.sparql_post_json", blocked_post)
    monkeypatch.setattr(
        "app.connectors.camera.sleep",
        lambda delay: (_ for _ in ()).throw(AssertionError("HTML must not be retried")),
    )

    with pytest.raises(RuntimeError, match="snapshot precedente conservata"):
        CameraConnector(prefer_snapshot=False, live_retry_attempts=3).fetch_live_documents()

    assert calls == 1


def test_camera_transient_errors_use_bounded_backoff(monkeypatch):
    calls = 0
    delays: list[float] = []

    def flaky_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("temporary transport error")
        return ROWS

    monkeypatch.setattr("app.connectors.camera.sparql_post_json", flaky_post)
    monkeypatch.setattr("app.connectors.camera.sleep", delays.append)

    documents = CameraConnector(prefer_snapshot=False, live_retry_attempts=3).fetch_live_documents()

    assert len(documents) == 2
    assert calls == 3
    assert delays == [2, 8]


def test_camera_query_requires_one_complete_row_per_act():
    query = _build_camera_query(
        "http://dati.camera.it/ocd/legislatura.rdf/repubblica_19",
        200,
    )

    assert "SELECT DISTINCT ?atto ?title ?date ?identifier" in query
    assert "dc:identifier ?identifier" in query
    assert "OPTIONAL" not in query
