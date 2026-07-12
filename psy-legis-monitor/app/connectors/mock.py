"""Realistic mock connector for MVP development and tests."""

from __future__ import annotations

from datetime import date, datetime

from app.connectors.base import BaseConnector
from app.core.schemas import LegislativeDocument


class MockConnector(BaseConnector):
    name = "mock"

    def fetch_documents(self) -> list[LegislativeDocument]:
        return [
            LegislativeDocument(
                source="Camera dei deputati - mock",
                source_type="mock",
                level="nazionale",
                act_type="proposta_di_legge",
                identifier="MOCK-AC-1001",
                title="Istituzione dello psicologo scolastico nelle scuole secondarie",
                summary="Proposta per sportelli di supporto psicologico stabili.",
                date_presented=date(2026, 5, 12),
                date_published=date(2026, 5, 13),
                last_update=datetime(2026, 5, 20, 10, 0),
                status="in_commissione",
                url="https://example.org/mock/psicologo-scolastico",
                text=(
                    "La proposta istituisce il servizio di psicologo scolastico "
                    "con sportello psicologico, consulenza psicologica e azioni "
                    "contro bullismo, cyberbullismo e disagio giovanile."
                ),
                metadata={"commissione": "Affari sociali", "legislatura": "XIX"},
            ),
            LegislativeDocument(
                source="Senato della Repubblica - mock",
                source_type="mock",
                level="nazionale",
                act_type="disegno_di_legge",
                identifier="MOCK-AS-2044",
                title="Rafforzamento dei servizi di salute mentale territoriale",
                summary="Misure per consultori, equipe multidisciplinari e presa in carico.",
                date_presented=date(2026, 4, 18),
                date_published=date(2026, 4, 19),
                last_update=datetime(2026, 5, 25, 15, 30),
                status="assegnato",
                url="https://example.org/mock/salute-mentale-territoriale",
                text=(
                    "Il disegno di legge potenzia salute mentale, servizi territoriali, "
                    "consultori, case della comunità e equipe multidisciplinare per "
                    "minori, adolescenti e famiglie."
                ),
                metadata={"commissione": "Sanita", "firmatari": ["Rossi", "Bianchi"]},
            ),
            LegislativeDocument(
                source="Gazzetta Ufficiale - mock",
                source_type="mock",
                level="nazionale",
                act_type="regolamento",
                identifier="MOCK-GU-77",
                title="Linee guida su intelligenza artificiale e dati sanitari",
                summary="Regole su algoritmi, telemedicina e consenso informato.",
                date_published=date(2026, 5, 30),
                last_update=datetime(2026, 5, 30, 9, 0),
                status="pubblicato",
                url="https://example.org/mock/ai-dati-sanitari",
                text=(
                    "Il regolamento disciplina sistemi automatizzati, intelligenza "
                    "artificiale, dati sanitari, privacy, consenso informato, "
                    "sanità digitale, telemedicina e chatbot in ambito sanitario."
                ),
                metadata={"numero": "77", "serie": "generale"},
            ),
            LegislativeDocument(
                source="Regione Veneto - mock",
                source_type="mock",
                level="regionale",
                region="Veneto",
                act_type="dgr",
                identifier="MOCK-VEN-DGR-12",
                title="Contributi per la manutenzione degli impianti sportivi comunali",
                summary="Misure finanziarie per impianti sportivi.",
                date_published=date(2026, 5, 28),
                last_update=datetime(2026, 5, 28, 12, 0),
                status="pubblicato",
                url="https://example.org/mock/impianti-sportivi",
                text=(
                    "La delibera assegna contributi ai comuni per la manutenzione "
                    "ordinaria di impianti sportivi e palestre."
                ),
                metadata={"bur": "45"},
            ),
        ]

