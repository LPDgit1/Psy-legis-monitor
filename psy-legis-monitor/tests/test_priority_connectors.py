from datetime import UTC, datetime

from app.connectors.camera import (
    CameraConnector,
    _camera_row_to_document,
    parse_camera_latest_bills,
    parse_camera_resource_rdf,
)
from app.connectors.normattiva import (
    parse_approved_not_published_laws,
    parse_normattiva_home_updates,
)
from app.connectors.regions.veneto import parse_veneto_bur_latest
from app.connectors.senato import _senato_row_to_document
from app.connectors.sparql import parse_sparql_json, parse_sparql_xml, sparql_query


def test_parse_sparql_xml_extracts_bindings():
    payload = """
    <sparql xmlns="http://www.w3.org/2005/sparql-results#">
      <head><variable name="atto"/><variable name="title"/></head>
      <results>
        <result>
          <binding name="atto"><uri>http://example.test/atto/1</uri></binding>
          <binding name="title"><literal>Proposta su consultori</literal></binding>
        </result>
      </results>
    </sparql>
    """

    rows = parse_sparql_xml(payload)

    assert rows == [{"atto": "http://example.test/atto/1", "title": "Proposta su consultori"}]


def test_parse_sparql_json_extracts_bindings():
    payload = """
    {
      "head": {"vars": ["atto", "title"]},
      "results": {
        "bindings": [
          {
            "atto": {"type": "uri", "value": "http://example.test/atto/1"},
            "title": {"type": "literal", "value": "Proposta su consultori"}
          }
        ]
      }
    }
    """

    rows = parse_sparql_json(payload)

    assert rows == [{"atto": "http://example.test/atto/1", "title": "Proposta su consultori"}]


def test_sparql_query_uses_post_json_on_httpx(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        text = """
        {
          "results": {
            "bindings": [
              {"title": {"type": "literal", "value": "DDL psicologia scolastica"}}
            ]
          }
        }
        """

        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs["data"]
        captured["headers"] = kwargs["headers"]
        return FakeResponse()

    monkeypatch.setattr("app.connectors.sparql.httpx.post", fake_post)

    rows = sparql_query("https://example.test/sparql", "SELECT ?title WHERE {}", method="httpx", timeout=12)

    assert rows == [{"title": "DDL psicologia scolastica"}]
    assert captured["url"] == "https://example.test/sparql"
    assert captured["data"] == {
        "query": "SELECT ?title WHERE {}",
        "format": "application/sparql-results+json",
    }
    assert "application/sparql-results+json" in captured["headers"]["Accept"]
    assert captured["headers"]["User-Agent"] == "psy-legis-monitor/0.1"


def test_sparql_query_auto_tries_post_before_get(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        text = """
        {
          "results": {
            "bindings": [
              {"title": {"type": "literal", "value": "A.C. salute mentale"}}
            ]
          }
        }
        """

        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs["data"]
        return FakeResponse()

    def fail_fetch_text(*args, **kwargs):
        raise AssertionError("GET fallback should not run when POST succeeds")

    monkeypatch.setattr("app.connectors.sparql.httpx.post", fake_post)
    monkeypatch.setattr("app.connectors.sparql.fetch_text", fail_fetch_text)

    rows = sparql_query("https://example.test/sparql", "SELECT ?title WHERE {}", method="auto", timeout=12)

    assert rows == [{"title": "A.C. salute mentale"}]
    assert captured["url"] == "https://example.test/sparql"
    assert captured["data"]["format"] == "application/sparql-results+json"


def test_sparql_query_auto_tries_powershell_post_after_httpx_html(monkeypatch):
    captured: dict[str, object] = {}

    class HtmlResponse:
        text = "<html><script>window.location.reload()</script></html>"

        def raise_for_status(self) -> None:
            return None

    class Completed:
        stdout = """
        {
          "results": {
            "bindings": [
              {"title": {"type": "literal", "value": "A.C. psicologia"}}
            ]
          }
        }
        """

    def fake_post(*args, **kwargs):
        return HtmlResponse()

    def fake_which(name: str):
        return "powershell.exe" if name == "powershell.exe" else None

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env_query"] = kwargs["env"]["PSY_LEGIS_SPARQL_QUERY"]
        return Completed()

    def fail_fetch_text(*args, **kwargs):
        raise AssertionError("GET fallback should not run when PowerShell POST succeeds")

    monkeypatch.setattr("app.connectors.sparql.httpx.post", fake_post)
    monkeypatch.setattr("app.connectors.sparql.shutil.which", fake_which)
    monkeypatch.setattr("app.connectors.sparql.subprocess.run", fake_run)
    monkeypatch.setattr("app.connectors.sparql.fetch_text", fail_fetch_text)

    rows = sparql_query("https://example.test/sparql", "SELECT ?title WHERE {}", method="auto", timeout=12)

    assert rows == [{"title": "A.C. psicologia"}]
    assert captured["env_query"] == "SELECT ?title WHERE {}"
    assert captured["command"][0] == "powershell.exe"
    assert "'User-Agent'='psy-legis-monitor/0.1'" in captured["command"][3]


def test_sparql_query_get_fallback_prefers_json(monkeypatch):
    captured: dict[str, str] = {}

    def fake_fetch_text(url: str, *, method: str, timeout: float) -> str:
        captured["url"] = url
        captured["method"] = method
        captured["timeout"] = str(timeout)
        return """
        {
          "results": {
            "bindings": [
              {"title": {"type": "literal", "value": "DDL psicologia scolastica"}}
            ]
          }
        }
        """

    monkeypatch.setattr("app.connectors.sparql.fetch_text", fake_fetch_text)

    rows = sparql_query("https://example.test/sparql", "SELECT ?title WHERE {}", method="powershell", timeout=12)

    assert rows == [{"title": "DDL psicologia scolastica"}]
    assert "format=json" in captured["url"]
    assert captured["method"] == "powershell"
    assert captured["timeout"] == "12"


def test_parse_sparql_json_rejects_html_cache_page():
    payload = """
    <html>
      <meta http-equiv="Pragma" content="no-cache"/>
      <script type="text/javascript">window.location.reload()</script>
    </html>
    """

    try:
        parse_sparql_json(payload)
    except ValueError as exc:
        assert "Risposta SPARQL in HTML" in str(exc)
        assert "pagina tecnica/cache" in str(exc)
    else:
        raise AssertionError("Expected HTML payload to be rejected")


def test_camera_row_maps_to_legislative_document():
    document = _camera_row_to_document(
        {
            "atto": "http://dati.camera.it/ocd/attocamera.rdf/ac19_3014",
            "title": "Disposizioni in materia di servizi psicologici territoriali",
            "description": "Proposta di legge presentata alla Camera",
            "date": "20260710",
            "identifier": "C.3014",
            "ref": "https://www.camera.it/leg19/126?tab=&leg=19&idDocumento=3014",
        },
        fetched_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )

    assert document.source_type == "official_api"
    assert document.identifier == "C.3014"
    assert document.date_presented.isoformat() == "2026-07-10"
    assert document.status == "presentato"


def test_parse_camera_latest_bills_extracts_official_html_fallback():
    html = """
    <section>
      <h5>Ultimi Progetti di Legge stampati</h5>
      <ul>
        <li>
          <a href="https://documenti.camera.it/leg19/pdl/pdf/leg.19.pdl.camera.2937.19PDL0154760.pdf">
            A.C. 2937
          </a>
          RAIMONDO ed altri: "Disposizioni per la semplificazione del procedimento di rinnovo
          del contrassegno europeo di parcheggio per le persone con disabilità nei casi di
          disabilità grave permanente e non rivedibile" (2937)
          Stampato il 09-07-2026
        </li>
      </ul>
    </section>
    """

    documents = parse_camera_latest_bills(
        html,
        "https://www.camera.it/leg19/141",
        fetched_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
        limit=10,
        sparql_error=RuntimeError("cache html"),
    )

    assert len(documents) == 1
    assert documents[0].source == "Camera dei deputati - Progetti di legge"
    assert documents[0].source_type == "html"
    assert documents[0].identifier == "A.C. 2937"
    assert documents[0].date_published.isoformat() == "2026-07-09"
    assert documents[0].metadata["fallback"] == "camera_latest_bills_html"
    assert "semplificazione del procedimento" in documents[0].title
    assert "A.C. 2937" not in documents[0].title


def test_parse_camera_latest_bills_reads_text_after_anchor_without_list_item():
    html = """
    <div>
      <a href="https://documenti.camera.it/leg19/pdl/pdf/test.pdf">A.C. 2997</a>
    </div>
    <p>
      PROPOSTA DI LEGGE D'INIZIATIVA POPOLARE:
      "Disposizioni in materia di governo dei flussi migratori" (2997)
    </p>
    <p>Stampato il 10-07-2026</p>
    <div>
      <a href="https://documenti.camera.it/leg19/pdl/pdf/next.pdf">A.C. 3006</a>
      "Disposizioni per l'assestamento del bilancio dello Stato" (3006)
      Stampato il 10-07-2026
    </div>
    """

    documents = parse_camera_latest_bills(
        html,
        "https://www.camera.it/leg19/141",
        fetched_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
        limit=10,
    )

    assert len(documents) == 2
    assert documents[0].identifier == "A.C. 2997"
    assert documents[0].date_published.isoformat() == "2026-07-10"
    assert "governo dei flussi migratori" in documents[0].title
    assert documents[1].identifier == "A.C. 3006"


def test_parse_camera_latest_bills_falls_back_to_full_page_text():
    html = """
    <main>
      Ultimi Progetti di Legge stampati
      A.C. 2952 MORRONE ed altri: "Modifiche al decreto legislativo 8 giugno 2001,
      n. 231, in materia di responsabilita delle persone giuridiche" (2952)
      Stampato il 10-07-2026
      A.C. 2997 PROPOSTA DI LEGGE D'INIZIATIVA POPOLARE:
      "Disposizioni in materia di governo dei flussi migratori" (2997)
      Stampato il 10-07-2026
    </main>
    """

    documents = parse_camera_latest_bills(
        html,
        "https://www.camera.it/leg19/141",
        fetched_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
        limit=10,
    )

    assert [document.identifier for document in documents] == ["A.C. 2952", "A.C. 2997"]
    assert documents[0].url == "https://www.camera.it/leg19/141"
    assert documents[0].date_published.isoformat() == "2026-07-10"
    assert "responsabilita delle persone giuridiche" in documents[0].title


def test_camera_connector_falls_back_to_latest_bills_page(monkeypatch):
    def fake_sparql_query(*args, **kwargs):
        raise RuntimeError("Risposta SPARQL in HTML invece che JSON")

    def fake_fetch_text(url: str, *, method: str, timeout: float) -> str:
        assert url == "https://www.camera.it/leg19/141"
        return """
        <ul>
          <li>
            <a href="/leg19/test">A.C. 3006</a>
            "Disposizioni per l'assestamento del bilancio dello Stato per l'anno finanziario 2026" (3006)
            Stampato il 10-07-2026
          </li>
        </ul>
        """

    monkeypatch.setattr("app.connectors.camera.sparql_query", fake_sparql_query)
    monkeypatch.setattr("app.connectors.camera.fetch_text", fake_fetch_text)

    documents = CameraConnector(
        fetch_method="httpx",
        limit=5,
        resource_fallback_enabled=False,
        prefer_snapshot=False,
    ).fetch_documents()

    assert len(documents) == 1
    assert documents[0].identifier == "A.C. 3006"
    assert documents[0].metadata["fallback"] == "camera_latest_bills_html"
    assert "SPARQL in HTML" in documents[0].metadata["sparql_error"]


def test_camera_connector_returns_empty_when_both_camera_paths_have_no_documents(monkeypatch):
    def fake_sparql_query(*args, **kwargs):
        raise RuntimeError("Risposta SPARQL in HTML invece che JSON")

    def fake_fetch_text(url: str, *, method: str, timeout: float) -> str:
        return "<html><body>Nessun progetto disponibile</body></html>"

    monkeypatch.setattr("app.connectors.camera.sparql_query", fake_sparql_query)
    monkeypatch.setattr("app.connectors.camera.fetch_text", fake_fetch_text)

    assert (
        CameraConnector(
            fetch_method="httpx",
            limit=5,
            resource_fallback_enabled=False,
            prefer_snapshot=False,
        ).fetch_documents()
        == []
    )


def test_parse_camera_resource_rdf_maps_official_resource():
    payload = """
    <?xml version="1.0"?>
    <rdf:RDF
        xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:dc="http://purl.org/dc/elements/1.1/"
        xmlns:dcterms="http://purl.org/dc/terms/">
      <rdf:Description rdf:about="http://dati.camera.it/ocd/attocamera.rdf/ac19_3015">
        <dc:title> LUPI: "Disposizioni concernenti l&amp;rsquo;attivita degli psicologi" (3015) </dc:title>
        <dcterms:isReferencedBy rdf:resource="http://www.camera.it/uri-res/test-3015"/>
        <dc:date>20260709</dc:date>
        <dc:type>Progetto di Legge</dc:type>
        <dc:identifier>3015</dc:identifier>
        <dc:creator>LUPI Maurizio</dc:creator>
      </rdf:Description>
    </rdf:RDF>
    """

    document = parse_camera_resource_rdf(
        payload,
        "https://dati.camera.it/ocd/attocamera.rdf/ac19_3015",
        fetched_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
        sparql_error=RuntimeError("SPARQL blocked"),
    )

    assert document is not None
    assert document.source_type == "official_api"
    assert document.identifier == "3015"
    assert document.date_presented.isoformat() == "2026-07-09"
    assert "attivita degli psicologi" in document.title
    assert document.metadata["fallback"] == "camera_resource_rdf"
    assert "SPARQL blocked" in document.metadata["sparql_error"]


def test_camera_connector_uses_rdf_resource_fallback_when_sparql_is_blocked(monkeypatch):
    rdf_payloads = {
        "2999": """
        <rdf:RDF
            xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
            xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:dcterms="http://purl.org/dc/terms/">
          <rdf:Description rdf:about="http://dati.camera.it/ocd/attocamera.rdf/ac19_2999">
            <dc:title>Proposta meno recente</dc:title>
            <dc:date>20260701</dc:date>
            <dc:identifier>2999</dc:identifier>
          </rdf:Description>
        </rdf:RDF>
        """,
        "3000": """
        <rdf:RDF
            xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
            xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:dcterms="http://purl.org/dc/terms/">
          <rdf:Description rdf:about="http://dati.camera.it/ocd/attocamera.rdf/ac19_3000">
            <dc:title>Disposizioni in materia di psicologia scolastica</dc:title>
            <dc:date>20260710</dc:date>
            <dc:identifier>3000</dc:identifier>
          </rdf:Description>
        </rdf:RDF>
        """,
    }

    def fake_sparql_query(*args, **kwargs):
        raise RuntimeError("Risposta SPARQL in HTML invece che JSON")

    def fake_resource_text(url: str, *, timeout: float) -> str:
        number = url.rsplit("_", 1)[-1]
        return rdf_payloads.get(
            number,
            """
            <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
              <rdf:Description rdf:about="http://dati.camera.it/ocd/attocamera.rdf/ac19_empty"/>
            </rdf:RDF>
            """,
        )

    def fail_fetch_text(*args, **kwargs):
        raise AssertionError("HTML fallback should not run when RDF fallback succeeds")

    monkeypatch.setattr("app.connectors.camera.sparql_query", fake_sparql_query)
    monkeypatch.setattr("app.connectors.camera._fetch_camera_resource_text", fake_resource_text)
    monkeypatch.setattr("app.connectors.camera.fetch_text", fail_fetch_text)

    documents = CameraConnector(
        fetch_method="httpx",
        limit=1,
        resource_fallback_enabled=True,
        resource_probe_start=2999,
        resource_probe_max=5,
        resource_probe_empty_stop=2,
        prefer_snapshot=False,
    ).fetch_documents()

    assert len(documents) == 1
    assert documents[0].identifier == "3000"
    assert documents[0].metadata["fallback"] == "camera_resource_rdf"


def test_camera_resource_fallback_skips_html_technical_payload(monkeypatch):
    from app.connectors.camera import fetch_camera_resource_documents

    valid_payload = """
    <rdf:RDF
        xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:dc="http://purl.org/dc/elements/1.1/">
      <rdf:Description rdf:about="http://dati.camera.it/ocd/attocamera.rdf/ac19_3001">
        <dc:title>Disposizioni in materia di servizi psicologici</dc:title>
        <dc:date>20260711</dc:date>
        <dc:identifier>3001</dc:identifier>
      </rdf:Description>
    </rdf:RDF>
    """

    def fake_resource_text(url: str, *, timeout: float) -> str:
        if url.endswith("_3000"):
            return "<html><script>window.location.reload()</script></html>"
        return valid_payload

    monkeypatch.setattr("app.connectors.camera._fetch_camera_resource_text", fake_resource_text)
    stats: dict[str, int] = {}

    documents = fetch_camera_resource_documents(
        legislature_uri="http://dati.camera.it/ocd/legislatura.rdf/repubblica_19",
        start=3000,
        max_resources=2,
        empty_stop=2,
        limit=5,
        timeout=10,
        fetched_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
        stats=stats,
    )

    assert len(documents) == 1
    assert documents[0].identifier == "3001"
    assert stats["html_payloads"] == 1


def test_camera_resource_fallback_stops_after_repeated_html_payloads(monkeypatch):
    from app.connectors.camera import fetch_camera_resource_documents

    def fake_resource_text(url: str, *, timeout: float) -> str:
        return "<html><script>window.location.reload()</script></html>"

    monkeypatch.setattr("app.connectors.camera._fetch_camera_resource_text", fake_resource_text)
    stats: dict[str, int] = {}

    documents = fetch_camera_resource_documents(
        legislature_uri="http://dati.camera.it/ocd/legislatura.rdf/repubblica_19",
        start=3000,
        max_resources=80,
        empty_stop=20,
        limit=5,
        timeout=10,
        fetched_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
        stats=stats,
        html_stop=4,
    )

    assert documents == []
    assert stats["probed"] == 4
    assert stats["html_payloads"] == 4


def test_camera_diagnostics_detects_browser_check_page(monkeypatch):
    def fake_sparql_query(*args, **kwargs):
        return [
            {
                "identifier": "3014",
                "title": "Disposizioni in materia di servizi psicologici",
            }
        ]

    def fake_fetch_text(url: str, *, method: str, timeout: float) -> str:
        return """
        <html><body>
        Checking your browser before accessing www.camera.it
        This process is automatic. Your browser will redirect to requested content shortly.
        </body></html>
        """

    monkeypatch.setattr("app.connectors.camera.sparql_query", fake_sparql_query)
    monkeypatch.setattr("app.connectors.camera.fetch_text", fake_fetch_text)

    diagnostics = CameraConnector(
        fetch_method="httpx",
        limit=5,
        resource_fallback_enabled=True,
    ).diagnose_fetch()

    assert diagnostics["diagnostic_schema_version"] == 9
    assert diagnostics["sparql_status"] == "ok"
    assert diagnostics["sparql_rows"] == 1
    assert diagnostics["sparql_sample_identifier"] == "3014"
    assert diagnostics["fallback_status"] == "blocked_by_browser_check"
    assert diagnostics["overall_status"].startswith("ok: dati.camera.it SPARQL raggiungibile")
    assert diagnostics["blocked_by_browser_check"] is True
    assert diagnostics["contains_ac_marker"] is False
    assert diagnostics["parsed_documents"] == 0


def test_camera_diagnostics_reports_rdf_resource_fallback(monkeypatch):
    def fake_sparql_query(*args, **kwargs):
        raise RuntimeError("Risposta SPARQL in HTML invece che JSON")

    def fake_resource_documents(**kwargs):
        return [
            _camera_row_to_document(
                {
                    "atto": "http://dati.camera.it/ocd/attocamera.rdf/ac19_3000",
                    "title": "Disposizioni in materia di psicologia scolastica",
                    "date": "20260710",
                    "identifier": "3000",
                },
                fetched_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
            )
        ]

    def fake_fetch_text(url: str, *, method: str, timeout: float) -> str:
        return """
        <html><body>
        Checking your browser before accessing www.camera.it
        This process is automatic. Your browser will redirect to requested content shortly.
        </body></html>
        """

    monkeypatch.setattr("app.connectors.camera.sparql_query", fake_sparql_query)
    monkeypatch.setattr("app.connectors.camera.fetch_camera_resource_documents", fake_resource_documents)
    monkeypatch.setattr("app.connectors.camera.fetch_text", fake_fetch_text)

    diagnostics = CameraConnector(
        fetch_method="httpx",
        limit=5,
        resource_fallback_enabled=True,
    ).diagnose_fetch()

    assert diagnostics["diagnostic_schema_version"] == 9
    assert diagnostics["sparql_status"] == "error"
    assert diagnostics["resource_status"] == "ok"
    assert diagnostics["resource_rows"] == 1
    assert diagnostics["resource_sample_identifier"] == "3000"
    assert diagnostics["fallback_status"] == "blocked_by_browser_check"
    assert diagnostics["overall_status"].startswith("ok: SPARQL bloccato, ma fallback RDF ufficiale")


def test_camera_diagnostics_reports_rdf_html_block_without_crashing(monkeypatch):
    def fake_sparql_query(*args, **kwargs):
        raise RuntimeError("Risposta SPARQL in HTML invece che JSON")

    def fake_resource_text(url: str, *, timeout: float) -> str:
        return "<html><script>window.location.reload()</script></html>"

    def fake_fetch_text(url: str, *, method: str, timeout: float) -> str:
        return """
        <html><body>
        Checking your browser before accessing www.camera.it
        This process is automatic. Your browser will redirect to requested content shortly.
        </body></html>
        """

    monkeypatch.setattr("app.connectors.camera.sparql_query", fake_sparql_query)
    monkeypatch.setattr("app.connectors.camera._fetch_camera_resource_text", fake_resource_text)
    monkeypatch.setattr("app.connectors.camera.fetch_text", fake_fetch_text)

    diagnostics = CameraConnector(
        fetch_method="httpx",
        limit=5,
        resource_fallback_enabled=True,
        resource_probe_start=3000,
        resource_probe_max=3,
        resource_probe_empty_stop=2,
    ).diagnose_fetch()

    assert diagnostics["diagnostic_schema_version"] == 9
    assert diagnostics["sparql_status"] == "error"
    assert diagnostics["resource_status"] == "html_blocked"
    assert diagnostics["resource_probe_html_payloads"] == 3
    assert diagnostics["resource_probe_html_stop"] == 5
    assert diagnostics["fallback_status"] == "blocked_by_browser_check"
    assert diagnostics["overall_status"].startswith("errore: SPARQL e risorse RDF Camera")
    assert "fonte manuale/opzionale" in diagnostics["recommended_strategy"]


def test_senato_row_maps_to_legislative_document():
    document = _senato_row_to_document(
        {
            "ddl": "http://dati.senato.it/ddl/60275",
            "idFase": "60275",
            "ramo": "S",
            "legislatura": "19",
            "numeroFase": "1953",
            "titolo": "Disposizioni in materia di salute mentale",
            "natura": "ordinario",
            "stato": "Da assegnare a commissione",
            "dataPresentazione": "2026-07-09",
            "dataStato": "2026-07-09",
        },
        fetched_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
        legislature=19,
    )

    assert document.identifier == "S.1953"
    assert document.act_type == "disegno_di_legge"
    assert document.date_presented.isoformat() == "2026-07-09"
    assert document.status == "in_commissione"
    assert document.url == "https://www.senato.it/leg/19/BGT/Schede/Ddliter/60275.htm"


def test_parse_normattiva_home_updates_extracts_multivigenza_item():
    html = """
    <section>
      <h3>"SALUTE MENTALE - DISPOSIZIONI URGENTI"</h3>
      <p>La Banca Dati e' aggiornata in multivigenza con le modifiche apportate dal
      <a href="/atto/decreto">Decreto-Legge 26 giugno 2026, n. 108</a>.</p>
      <a href="/news/salute-mentale">Leggi di piu</a>
      <p>9 luglio 2026</p>
    </section>
    """

    documents = parse_normattiva_home_updates(
        html,
        "https://www.normattiva.it/",
        fetched_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )

    assert len(documents) == 1
    assert documents[0].title == "SALUTE MENTALE - DISPOSIZIONI URGENTI"
    assert documents[0].act_type == "decreto_legge"
    assert documents[0].date_published.isoformat() == "2026-07-09"
    assert documents[0].url == "https://www.normattiva.it/atto/decreto"


def test_parse_approved_not_published_laws_extracts_bill_identifiers():
    html = """
    <main>
      <h1>Progetti di legge approvati non promulgati o pubblicati</h1>
      <ul><li>Revisione delle modalita di accesso alla docenza universitaria</li></ul>
      <a href="https://documenti.camera.it/testi/approvato.pdf">
        Testo definitivamente approvato dalla Camera il 7 luglio 2026
      </a>
      Iter e lavori preparatori <a href="/leg/19/BGT/Schede/Ddliter/1518.htm">S.1518</a>
      <a href="/leg/19/BGT/Schede/Ddliter/2735.htm">C.2735</a>
    </main>
    """

    documents = parse_approved_not_published_laws(
        html,
        "https://www.parlamento.it/leg/ldl_new/v3/sldlelencoddlappnonpub.htm",
        fetched_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )

    assert len(documents) == 1
    assert documents[0].status == "approvato"
    assert documents[0].date_presented.isoformat() == "2026-07-07"
    assert documents[0].metadata["bill_identifiers"] == ["S.1518", "C.2735"]


def test_parse_veneto_bur_latest_maps_latest_issues():
    html = """
    <html><body>
      <h3>Ultime uscite</h3>
      <p>BUR N. 78 del 19/06/2026</p>
      <p>BUR N. 79 del 19/06/2026</p>
    </body></html>
    """

    documents = parse_veneto_bur_latest(
        html,
        "https://bur.regione.veneto.it/",
        fetched_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )

    assert [document.identifier for document in documents] == [
        "BUR Veneto n. 78/2026",
        "BUR Veneto n. 79/2026",
    ]
    assert documents[0].date_published.isoformat() == "2026-06-19"
