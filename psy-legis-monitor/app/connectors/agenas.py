"""Connector for AGENAS institutional updates relevant to health governance."""

from __future__ import annotations

from app.connectors.configured_pages import ConfiguredPageGroupConnector


class AgenasConnector(ConfiguredPageGroupConnector):
    name = "agenas"
    config_key = "agenas"
    default_sources = [
        {
            "name": "AGENAS - Home e aree tematiche",
            "enabled": True,
            "source": "AGENAS - Agenzia Nazionale per i Servizi Sanitari Regionali",
            "level": "nazionale",
            "act_type": "altro",
            "status": "pubblicato",
            "url": "https://www.agenas.gov.it/",
            "source_type": "html",
            "fetch_method": "auto",
            "max_items": 40,
            "include_patterns": [
                "Primo piano",
                "Comunicati Stampa",
                "LEA",
                "Livelli Essenziali",
                "Fabbisogno del Personale Sanitario",
                "Accreditamento",
                "Rischio clinico",
                "Umanizzazione",
                "HTA",
                "ECM",
                "PNRR",
                "Telemedicina",
                "PNE",
            ],
            "exclude_patterns": [
                "Cookie",
                "Privacy",
                "Facebook",
                "Twitter",
                "Youtube",
                "Linkedin",
            ],
        }
    ]
