"""Connector for Regione Lombardia BURL and normative entry points."""

from __future__ import annotations

from app.connectors.configured_pages import ConfiguredPageGroupConnector


class LombardiaConnector(ConfiguredPageGroupConnector):
    """Fetch configured Regione Lombardia BURL and normative links."""

    name = "regione_lombardia"
    config_key = "regione_lombardia"
    default_sources = [
        {
            "name": "Regione Lombardia - BURL",
            "enabled": True,
            "source": "Regione Lombardia - Bollettino Ufficiale",
            "level": "regionale",
            "region": "Lombardia",
            "act_type": "bur",
            "status": "pubblicato",
            "url": "https://www.consultazioniburl.servizirl.it/ConsultazioneBurl/",
            "source_type": "html",
            "fetch_method": "auto",
            "max_items": 30,
            "include_patterns": [
                "BURL",
                "Bollettino",
                "Serie Ordinaria",
                "Serie Avvisi",
                "legge regionale",
                "deliberazione",
                "sanita",
                "salute",
                "sociale",
                "psicolog",
            ],
            "exclude_patterns": ["Cookie", "Privacy"],
        },
        {
            "name": "Regione Lombardia - Normativa",
            "enabled": True,
            "source": "Regione Lombardia - Normativa",
            "level": "regionale",
            "region": "Lombardia",
            "act_type": "altro",
            "status": "pubblicato",
            "url": "https://www.regione.lombardia.it/wps/portal/istituzionale/HP/istituzione/Normativa",
            "source_type": "html",
            "fetch_method": "auto",
            "max_items": 20,
            "include_patterns": [
                "legge regionale",
                "regolamento",
                "deliberazione",
                "sanita",
                "salute",
                "welfare",
                "sociale",
                "psicolog",
            ],
            "exclude_patterns": ["Cookie", "Privacy"],
        },
    ]
