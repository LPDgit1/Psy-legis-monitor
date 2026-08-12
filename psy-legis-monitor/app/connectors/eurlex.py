"""Connector for official EUR-Lex legislation RSS feeds."""

from __future__ import annotations

from app.config.settings import load_yaml, settings
from app.connectors.base import BaseConnector
from app.connectors.rss import RSSConnector
from app.core.schemas import LegislativeDocument
from app.core.text_cleaning import fold_for_search


DEFAULT_FEEDS = [
    {
        "name": "EUR-Lex - legislazione Parlamento e Consiglio",
        "source": "EUR-Lex - legislazione Parlamento e Consiglio",
        "url": "https://eur-lex.europa.eu/IT/display-feed.rss?rssId=162",
    },
    {
        "name": "EUR-Lex - atti Gazzetta ufficiale L",
        "source": "EUR-Lex - Gazzetta ufficiale dell'Unione europea",
        "url": "https://eur-lex.europa.eu/IT/display-feed.rss?rssId=165",
    },
]

DIRECT_TERMS = (
    "psicolog",
    "psicoterap",
    "salute mentale",
    "mental health",
    "neuropsic",
    "dipendenze patologiche",
    "disturbi alimentari",
    "suicidio",
    "autismo",
)

CONTEXT_GROUPS = (
    ("sanita", "salute", "health", "assistenza sanitaria"),
    ("minori", "children", "adolescent", "infanzia", "famiglia"),
    ("dati sanitari", "health data", "privacy", "intelligenza artificiale", "ai act"),
    ("disabilita", "disability", "caregiver", "vittime", "violenza di genere"),
    ("prevenzione", "servizi sociali", "welfare", "riabilitazione"),
)

NOISE_TERMS = (
    "veterinar",
    "animal health",
    "peste suina",
    "avian influenza",
    "mangimi",
    "feed hygiene",
    "fitosanitari",
)


class EurLexConnector(BaseConnector):
    """Read stable official RSS feeds instead of the challenge-prone homepage."""

    name = "eurlex"

    def __init__(self, feeds: list[dict] | None = None) -> None:
        section = load_yaml(settings.sources_path).get("eurlex", {})
        self.enabled = section.get("enabled", True)
        self.feeds = feeds or section.get("feeds") or DEFAULT_FEEDS

    def fetch_documents(self) -> list[LegislativeDocument]:
        if not self.enabled:
            return []
        documents: list[LegislativeDocument] = []
        errors: list[Exception] = []
        for feed in self.feeds:
            source_config = {
                **feed,
                "enabled": True,
                "source_type": "rss",
                "level": "europeo",
                "act_type": "altro",
                "status": "pubblicato",
                "fetch_method": feed.get("fetch_method", "auto"),
                "timeout": feed.get("timeout", 30),
            }
            try:
                documents.extend(RSSConnector(source_config).fetch_documents())
            except Exception as exc:
                errors.append(exc)
        relevant = [document for document in documents if is_relevant_eurlex_document(document)]
        if relevant or not errors:
            return _deduplicate(relevant)
        raise RuntimeError("EUR-Lex non interrogabile tramite i feed RSS ufficiali") from errors[0]


def is_relevant_eurlex_document(document: LegislativeDocument) -> bool:
    folded = fold_for_search(" ".join([document.title, document.summary or "", document.text]))
    has_direct = any(term in folded for term in DIRECT_TERMS)
    if any(term in folded for term in NOISE_TERMS) and not has_direct:
        return False
    if has_direct:
        return True
    return sum(any(term in folded for term in group) for group in CONTEXT_GROUPS) >= 2


def _deduplicate(documents: list[LegislativeDocument]) -> list[LegislativeDocument]:
    result: list[LegislativeDocument] = []
    seen: set[str] = set()
    for document in documents:
        key = str(document.identifier or document.url or document.title)
        if key in seen:
            continue
        seen.add(key)
        result.append(document)
    return result
