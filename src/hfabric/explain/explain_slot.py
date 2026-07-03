from __future__ import annotations

import re
import time

from langchain_core.language_models import BaseChatModel

from hfabric.contracts import KGProtocol
from hfabric.schemas import (
    EvidenceChunk,
    ExplainedHypothesis,
    KGNode,
    ScoredHypothesis,
    TraceRecord,
)

_PROMPT_TEMPLATE = """You are a metallurgy research analyst. For the following hypothesis, provide:

1. JUSTIFICATION: Why this hypothesis is plausible, citing the provided evidence. (2-3 sentences)
2. UNCERTAINTY: What gaps, assumptions, or unknowns exist. (1-2 sentences)
3. VERIFICATION PLAN: How to experimentally test this hypothesis. (1-2 sentences)

Hypothesis: {claim}
Mechanism: {mechanism}
Expected effect: {expected_effect}
Evidence: {chunk_texts}
Score: {score} (novelty={novelty}, feasibility={feasibility}, effect={effect})

Respond in this exact format:
JUSTIFICATION: <text>
UNCERTAINTY: <text>
VERIFICATION: <text>"""

_SECTION_MARKERS = {
    "JUSTIFICATION:": "justification",
    "UNCERTAINTY:": "uncertainty",
    "VERIFICATION:": "verification_plan",
}

_FALLBACK_JUSTIFICATION = "Based on the evidence provided."
_FALLBACK_UNCERTAINTY = "Unknown."
_FALLBACK_VERIFICATION = "Experimental validation recommended."

_STOPWORDS = {
    "the", "and", "for", "why", "how", "what", "this", "that",
    "with", "from", "are", "not", "has", "was", "can", "but",
    "its", "may", "due", "via",
}


def _extract_entity_names(text: str) -> list[str]:
    names: set[str] = set()

    capitalized = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
    for phrase in capitalized:
        names.add(phrase.lower())

    chemical = re.findall(r"\b[A-Z][a-z]?\b", text)
    for sym in chemical:
        if len(sym) >= 2:
            names.add(sym.lower())

    all_words = re.findall(r"\b[a-zA-Z]{2,}\b", text)
    for w in all_words:
        names.add(w.lower())

    return [n for n in names if n not in _STOPWORDS]


def _parse_llm_response(response: str) -> tuple[str, str, str]:
    justification = _FALLBACK_JUSTIFICATION
    uncertainty = _FALLBACK_UNCERTAINTY
    verification_plan = _FALLBACK_VERIFICATION

    positions = []
    for marker, key in _SECTION_MARKERS.items():
        idx = response.find(marker)
        if idx >= 0:
            positions.append((idx, marker, key))

    positions.sort()

    for i, (pos, marker, key) in enumerate(positions):
        if i + 1 < len(positions):
            end_pos = positions[i + 1][0]
        else:
            end_pos = len(response)

        start = pos + len(marker)
        section_text = response[start:end_pos].strip()

        if section_text:
            if key == "justification":
                justification = section_text
            elif key == "uncertainty":
                uncertainty = section_text
            elif key == "verification_plan":
                verification_plan = section_text

    return justification, uncertainty, verification_plan


def _build_kg_neighbourhood(
    scored: ScoredHypothesis,
    kg: KGProtocol,
) -> list[str]:
    lines: list[str] = []
    seen_entities: set[str] = set()

    entity_names = _extract_entity_names(scored.hypothesis.claim)

    for chunk in scored.cited_refs.values():
        entity_names.extend(_extract_entity_names(chunk.text))

    entity_names = list(dict.fromkeys(entity_names))

    for name in entity_names:
        try:
            entities = kg.get_entities(name)
        except Exception:
            continue

        for entity in entities:
            if entity.id in seen_entities:
                continue
            seen_entities.add(entity.id)

            entity_name = entity.properties.get("name", entity.id)
            lines.append(f"{entity.label}: {entity_name}")

            try:
                neighbours = kg.neighbours(entity.id, hops=2)
            except Exception:
                continue

            for nb in neighbours:
                if nb.id in seen_entities:
                    continue
                seen_entities.add(nb.id)

                nb_name = nb.properties.get("name", nb.id)
                lines.append(f"influences: {entity_name} -> {nb_name}")

    return lines


class ExplainSlot:
    def __init__(self, llm: BaseChatModel):
        self._llm = llm

    def explain(
        self,
        ranked: list[ScoredHypothesis],
        evidence_map: dict[str, EvidenceChunk] | list[EvidenceChunk],
        kg: KGProtocol,
        trace: TraceRecord | None = None,
    ) -> list[ExplainedHypothesis]:
        if isinstance(evidence_map, dict):
            evidence_list = list(evidence_map.values())
        else:
            evidence_list = evidence_map

        t0 = time.time()
        results: list[ExplainedHypothesis] = []

        for scored in ranked:
            neighbourhood_lines = _build_kg_neighbourhood(scored, kg)

            chunk_texts = "\n".join(
                f"[{cid}] {chunk.text}"
                for cid, chunk in scored.cited_refs.items()
            )

            hyp = scored.hypothesis
            features = scored.features
            prompt = _PROMPT_TEMPLATE.format(
                claim=hyp.claim,
                mechanism=hyp.mechanism,
                expected_effect=hyp.expected_effect,
                chunk_texts=chunk_texts or "(no evidence)",
                score=scored.score,
                novelty=features.get("novelty", 0.0),
                feasibility=features.get("feasibility", 0.0),
                effect=features.get("effect", 0.0),
            )

            try:
                response = self._llm.invoke(prompt)
                response_text = response.content if hasattr(response, "content") else str(response)
                justification, uncertainty, verification_plan = _parse_llm_response(response_text)
                token_in = len(prompt)
                token_out = len(response_text)
            except Exception:
                justification = _FALLBACK_JUSTIFICATION
                uncertainty = _FALLBACK_UNCERTAINTY
                verification_plan = _FALLBACK_VERIFICATION
                token_in = len(prompt)
                token_out = 0

            if trace is not None:
                trace.token_in += token_in
                trace.token_out += token_out

            results.append(
                ExplainedHypothesis(
                    scored=scored,
                    justification=justification,
                    uncertainty=uncertainty,
                    verification_plan=verification_plan,
                    graph_neighbourhood=neighbourhood_lines,
                )
            )

        latency_ms = (time.time() - t0) * 1000
        if trace is not None:
            trace.latency_ms += latency_ms

        return results
