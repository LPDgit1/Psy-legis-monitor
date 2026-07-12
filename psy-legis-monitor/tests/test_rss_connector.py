from xml.etree import ElementTree

from app.connectors.rss import RSSConnector


def test_rss_connector_maps_item_to_document():
    item = ElementTree.fromstring(
        """
        <item>
          <title>Nuova comunicazione CNOP su telepsicologia</title>
          <description>Indicazioni istituzionali per professionisti.</description>
          <link>https://www.psy.it/example</link>
          <guid>cnop-1</guid>
          <pubDate>Tue, 23 Jun 2026 10:00:00 +0000</pubDate>
        </item>
        """
    )
    connector = RSSConnector(
        {
            "name": "CNOP - News",
            "source": "CNOP",
            "level": "nazionale",
            "act_type": "altro",
            "status": "pubblicato",
        }
    )

    document = connector._item_to_document(item)

    assert document.source == "CNOP"
    assert document.identifier == "cnop-1"
    assert document.date_published.isoformat() == "2026-06-23"
    assert document.url == "https://www.psy.it/example"
