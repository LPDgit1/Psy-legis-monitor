"""Optional LLM classification with strict JSON validation."""

from __future__ import annotations

import json
import os

import httpx

from app.config.settings import settings
from app.core.schemas import LegislativeDocument, LLMClassificationResult


SYSTEM_PROMPT = (
    "Sei un assistente di analisi normativa per un Ordine professionale degli "
    "psicologi. Valuta se l'atto e rilevante per la psicologia professionale. "
    "Non inventare contenuti non presenti nel testo. Distingui tra citazione "
    "diretta, rilevanza indiretta, impatto sulle professioni sanitarie/"
    "ordinistiche e assenza di rilevanza. Restituisci solo JSON valido."
)


def build_llm_payload(document: LegislativeDocument, max_text_chars: int = 6000) -> str:
    relevant_input = {
        "titolo": document.title,
        "fonte": document.source,
        "stato": document.status,
        "summary": document.summary,
        "testo_troncato": document.text[:max_text_chars],
    }
    return json.dumps(relevant_input, ensure_ascii=False)


def classify_with_optional_llm(
    document: LegislativeDocument,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMClassificationResult | None:
    """Call an external LLM only when explicitly enabled by OPENAI_API_KEY."""

    key = api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        return None

    selected_model = model or settings.openai_model
    schema_instruction = (
        "Rispondi con JSON contenente: relevance_score, relevance_class, "
        "direct_mentions, domains, impact_type, relevant_passages, summary, "
        "why_relevant, risks, opportunities, recommended_action."
    )
    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": selected_model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"{schema_instruction}\n\n{build_llm_payload(document)}",
                },
            ],
            "text": {"format": {"type": "json_object"}},
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    output_text = payload.get("output_text")
    if not output_text:
        output = payload.get("output", [])
        output_text = output[0]["content"][0]["text"] if output else "{}"
    return LLMClassificationResult.model_validate_json(output_text)

