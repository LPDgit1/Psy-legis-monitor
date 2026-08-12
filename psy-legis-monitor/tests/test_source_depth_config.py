from app.connectors.gazzetta import GazzettaConnector
from app.connectors.regions.bur import load_regional_bur_sources
from app.connectors.senato import SenatoConnector


def test_priority_sources_scan_a_broader_recent_window():
    gazzetta_limits = {
        series.name: series.max_issues for series in GazzettaConnector.from_config_file()
    }
    regional_sources = load_regional_bur_sources()

    assert gazzetta_limits == {
        "Serie Generale": 10,
        "3a Serie Speciale - Regioni": 6,
    }
    assert SenatoConnector().limit == 60
    assert len(regional_sources) == 20
    assert all(source.max_items == 20 for source in regional_sources)
    assert all(source.max_detail_links == 3 for source in regional_sources)
    assert all(source.max_pdf_links == 2 for source in regional_sources)
    assert all(source.max_pdf_pages == 16 for source in regional_sources)
