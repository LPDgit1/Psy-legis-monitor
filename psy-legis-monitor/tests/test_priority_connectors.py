from datetime import UTC, datetime

from app.connectors.camera import _camera_row_to_document
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


def test_sparql_query_prefers_json(monkeypatch):
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

    rows = sparql_query("https://example.test/sparql", "SELECT ?title WHERE {}", method="httpx", timeout=12)

    assert rows == [{"title": "DDL psicologia scolastica"}]
    assert "format=json" in captured["url"]
    assert captured["method"] == "httpx"
    assert captured["timeout"] == "12"


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
