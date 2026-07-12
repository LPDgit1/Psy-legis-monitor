"""Connector for Ministero della Salute institutional normative pages."""

from __future__ import annotations

from app.connectors.configured_pages import ConfiguredPageGroupConnector
from app.connectors.trovanorme_salute import TrovaNormeSaluteConnector
from app.core.schemas import LegislativeDocument


class MinisteroSaluteConnector(ConfiguredPageGroupConnector):
    name = "ministero_salute"
    config_key = "ministero_salute"
    default_sources = [
        {
            "name": "Ministero Salute - Norme e atti",
            "enabled": True,
            "source": "Ministero della Salute - Norme e atti",
            "level": "nazionale",
            "act_type": "altro",
            "status": "pubblicato",
            "url": "https://www.salute.gov.it/new/it/sezione/norme-e-atti/",
            "source_type": "html",
            "fetch_method": "auto",
            "max_items": 40,
            "include_patterns": [
                "norme",
                "atti",
                "decreto",
                "ordinanza",
                "linee guida",
                "professioni sanitarie",
                "salute mentale",
                "bonus psicologo",
                "consultori",
                "telemedicina",
                "fascicolo sanitario",
                "PNRR",
                "LEA",
            ],
            "exclude_patterns": [
                "Cookie",
                "Privacy",
                "Facebook",
                "Instagram",
                "Youtube",
                "Linkedin",
            ],
        }
    ]

    def fetch_documents(self) -> list[LegislativeDocument]:
        documents: list[LegislativeDocument] = []
        errors: list[Exception] = []

        try:
            documents.extend(super().fetch_documents())
        except Exception as exc:
            errors.append(exc)

        try:
            documents.extend(TrovaNormeSaluteConnector().fetch_documents())
        except Exception as exc:
            errors.append(exc)

        if documents:
            return documents
        if errors:
            raise RuntimeError("Ministero Salute non interrogabile dalle fonti configurate") from errors[0]
        return []
