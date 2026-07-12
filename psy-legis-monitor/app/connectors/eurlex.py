"""Connector for EUR-Lex official EU law entry points."""

from __future__ import annotations

from app.connectors.configured_pages import ConfiguredPageGroupConnector


class EurLexConnector(ConfiguredPageGroupConnector):
    name = "eurlex"
    config_key = "eurlex"
    default_sources = [
        {
            "name": "EUR-Lex - Gazzetta ufficiale UE",
            "enabled": True,
            "source": "EUR-Lex - Gazzetta ufficiale dell'Unione europea",
            "level": "europeo",
            "act_type": "altro",
            "status": "pubblicato",
            "url": "https://eur-lex.europa.eu/homepage.html?locale=it",
            "source_type": "html",
            "fetch_method": "auto",
            "max_items": 30,
            "include_patterns": [
                "Serie L della GU",
                "Serie C della GU",
                "Atti giuridici",
                "Documenti preparatori",
                "Procedure normative",
                "Regolamento",
                "Direttiva",
                "Decisione",
                "salute",
                "dati",
                "AI",
            ],
            "exclude_patterns": [
                "Cookie",
                "Connettersi",
                "Registrarsi",
                "Aiuto",
            ],
        }
    ]
