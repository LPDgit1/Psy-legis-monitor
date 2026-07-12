"""Explainable alert generation."""

from __future__ import annotations

from app.core.hashing import document_identity_key
from app.core.schemas import Alert, LegislativeDocument, ScoreResult, TaxonomyClassification


DIRECT_CATEGORIES = {"professione_diretta", "servizi_psicologici"}
STRATEGIC_DOMAINS = {
    "privacy_dati_sanitari_sanita_digitale",
    "intelligenza_artificiale_tecnologie_psicologiche",
}


def build_alert(
    document: LegislativeDocument,
    score: ScoreResult,
    taxonomy: TaxonomyClassification,
) -> Alert | None:
    if score.relevance_class == "irrilevante":
        return None

    direct_hit = bool(DIRECT_CATEGORIES & set(score.found_terms.keys()))
    strategic_hit = bool(STRATEGIC_DOMAINS & set(taxonomy.domains))
    domains = taxonomy.domains

    if direct_hit:
        level = "rosso"
        action = "nota_tecnica" if document.status == "pubblicato" else "proposta_emendamento"
        reason = "Rilevanza diretta per servizi, competenze o professione psicologica."
    elif score.relevance_class in {"alta", "media"}:
        level = "arancione"
        action = "monitoraggio"
        reason = "Rilevanza indiretta significativa per ambiti di intervento psicologico."
    elif strategic_hit:
        level = "blu"
        action = "monitoraggio"
        reason = "Rilevanza strategica per tecnologia, dati sanitari o scenario istituzionale."
    else:
        return None

    return Alert(
        document_key=document_identity_key(document),
        level=level,
        reason=reason,
        domains=domains,
        recommended_action=action,
    )

