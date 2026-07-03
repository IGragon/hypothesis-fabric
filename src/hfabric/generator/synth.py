from __future__ import annotations

import time
from typing import TYPE_CHECKING

from pydantic import BaseModel

from hfabric.config import MVPConfig
from hfabric.schemas import EvidenceChunk, Hypothesis, KPIParsed, TraceRecord

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


class HypothesisList(BaseModel):
    hypotheses: list[Hypothesis]


_MIN_FIELD_LENGTH = 10


def _validate_hypothesis(h: Hypothesis, valid_ids: set[str]) -> list[str]:
    errors: list[str] = []

    if not h.evidence_refs:
        errors.append(f"Hypothesis '{h.claim[:50]}...' has empty evidence_refs")

    for ref in h.evidence_refs:
        if ref not in valid_ids:
            errors.append(
                f"Hypothesis '{h.claim[:50]}...' references unknown chunk_id '{ref}'"
            )

    if len(h.claim) < _MIN_FIELD_LENGTH:
        errors.append(
            f"Hypothesis claim too short ({len(h.claim)} chars, min {_MIN_FIELD_LENGTH})"
        )
    if len(h.mechanism) < _MIN_FIELD_LENGTH:
        errors.append(
            f"Hypothesis mechanism too short ({len(h.mechanism)} chars, min {_MIN_FIELD_LENGTH})"
        )
    if len(h.expected_effect) < _MIN_FIELD_LENGTH:
        errors.append(
            f"Hypothesis expected_effect too short ({len(h.expected_effect)} chars, min {_MIN_FIELD_LENGTH})"
        )

    return errors


def _build_prompt(evidence: list[EvidenceChunk], kpi: KPIParsed) -> dict[str, str]:
    evidence_lines: list[str] = []
    for chunk in evidence:
        evidence_lines.append(f"- [{chunk.chunk_id}] {chunk.text}")

    evidence_text = "\n".join(evidence_lines)

    system_prompt = (
        "You are a metallurgy research assistant. "
        "Generate research hypotheses based on the provided evidence."
    )

    user_prompt = f"""Research Goal: {kpi.goal}
KPI: {kpi.kpi.metric} — {kpi.kpi.direction} (target: {kpi.kpi.target or 'N/A'})
Constraints: {', '.join(kpi.constraints) if kpi.constraints else 'none'}
Language: {kpi.language}

Evidence chunks:
{evidence_text}

Instructions:
1. Generate 3-7 research hypotheses based on the evidence above.
2. Each hypothesis MUST include:
   - claim: a clear, specific statement of what should be tested
   - mechanism: explanation of how/why it works
   - expected_effect: the predicted outcome (quantitative if possible)
3. Each hypothesis MUST reference at least one evidence chunk by its chunk_id in evidence_refs.
4. Output in the language specified: {kpi.language}
5. Follow the constraints listed above.
6. Only propose hypotheses that the evidence actually supports."""

    return {"system": system_prompt, "user": user_prompt}


def _format_retry_prompt(original_prompt: str, errors: list[str]) -> str:
    error_details = "\n".join(f"  - {e}" for e in errors)
    return (
        f"{original_prompt}\n\n"
        f"PREVIOUS ATTEMPT WAS INVALID. Errors:\n{error_details}\n\n"
        f"Please regenerate. Ensure all hypotheses have non-empty fields "
        f"(claim, mechanism, expected_effect each >= {_MIN_FIELD_LENGTH} chars) "
        f"and valid evidence_refs that match provided chunk_ids."
    )


class CandidateSynthesizer:
    def __init__(self, llm: BaseChatModel, config: MVPConfig | None = None):
        self._llm = llm
        self._config = config or MVPConfig()
        self._structured = llm.with_structured_output(
            HypothesisList, method="json_schema"
        )

    def generate(
        self,
        evidence: list[EvidenceChunk],
        kpi: KPIParsed,
        trace: TraceRecord | None = None,
    ) -> list[Hypothesis]:
        if not evidence:
            return []

        valid_ids = {c.chunk_id for c in evidence}
        prompt = _build_prompt(evidence, kpi)
        current_prompt = prompt["user"]
        messages = [
            ("system", prompt["system"]),
            ("user", current_prompt),
        ]

        t0 = time.perf_counter()
        token_in_total = 0
        token_out_total = 0

        for attempt in range(self._config.fe2_max_reprompt + 1):
            try:
                result: HypothesisList = self._structured.invoke(messages)
            except Exception:
                if attempt < self._config.fe2_max_reprompt:
                    current_prompt = _format_retry_prompt(prompt["user"], ["LLM invocation failed"])
                    messages[-1] = ("user", current_prompt)
                    continue
                latency_ms = (time.perf_counter() - t0) * 1000
                if trace:
                    trace.token_in = token_in_total
                    trace.token_out = token_out_total
                    trace.latency_ms = latency_ms
                    trace.status = "error"
                return []

            hypotheses = result.hypotheses

            errors: list[str] = []
            for h in hypotheses:
                errors.extend(_validate_hypothesis(h, valid_ids))

            if not errors:
                latency_ms = (time.perf_counter() - t0) * 1000
                if trace:
                    trace.token_in = token_in_total
                    trace.token_out = token_out_total
                    trace.latency_ms = latency_ms
                    trace.status = "ok"
                return hypotheses

            if attempt < self._config.fe2_max_reprompt:
                current_prompt = _format_retry_prompt(prompt["user"], errors)
                messages[-1] = ("user", current_prompt)

        latency_ms = (time.perf_counter() - t0) * 1000
        if trace:
            trace.token_in = token_in_total
            trace.token_out = token_out_total
            trace.latency_ms = latency_ms
            trace.status = "error"
        return []
