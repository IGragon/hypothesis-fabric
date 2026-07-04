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
        "Вы — исследователь-металлург. Сгенерируйте научно-обоснованные гипотезы на основе "
        "предоставленных доказательств. Каждая гипотеза должна строго соответствовать "
        "указанным ограничениям и опираться на конкретные фрагменты доказательств. "
        "Выведите результат как валидный JSON-объект."
    )

    constraints_block = (
        "\n".join(f"  - {c}" for c in kpi.constraints) if kpi.constraints else "  (нет ограничений)"
    )

    user_prompt = f"""Исследовательская задача: {kpi.goal}
KPI: {kpi.kpi.metric} — {kpi.kpi.direction} (целевое значение: {kpi.kpi.target or 'N/A'})
Ограничения:
{constraints_block}
Язык вывода: {kpi.language}

Фрагменты доказательств (цитируйте по идентификатору [chunk_id]):
{evidence_text}

Инструкции:
1. Сгенерируйте 3-7 исследовательских гипотез на основе доказательств выше.
2. КАЖДАЯ гипотеза ОБЯЗАНА включать:
   - claim: чёткое, конкретное утверждение того, что нужно проверить
   - mechanism: объяснение, как/почему это работает
   - expected_effect: предсказанный результат (количественный, если возможно)
   - verification_plan: краткий план проверки (шаги, критерии успеха)
3. КАЖДАЯ гипотеза ОБЯЗАНА ссылаться хотя бы на один фрагмент доказательств по его chunk_id \
в поле evidence_refs. Идентификаторы имеют вид chunk_0007, chunk_0012 и т.д. — используйте \
их в точности как показано выше.
4. НЕ предлагайте оборудование или методы, не входящие в список ограничений. \
Если в ограничениях указано «доступное оборудование: …», используйте ТОЛЬКО перечисленное оборудование.
5. Если KPI упоминает несколько металлов (например, медь и никель), КАЖДАЯ гипотеза должна \
адресовать оба металла или явно указать, почему фокусируется на одном.
6. Соблюдайте перечисленные ограничения. Бюджетные ограничения означают, что нельзя предлагать \
капиталоёмкие решения (новое оборудование, крупные перестройки).
7. Предлагайте только гипотезы, которые реально поддерживаются доказательствами.
8. Пишите на языке: {kpi.language}."""

    return {"system": system_prompt, "user": user_prompt}


def _format_retry_prompt(original_prompt: str, errors: list[str]) -> str:
    error_details = "\n".join(f"  - {e}" for e in errors)
    return (
        f"{original_prompt}\n\n"
        f"ПРЕДЫДУЩАЯ ПОПЫТКА БЫЛА НЕКОРРЕКТНОЙ. Ошибки:\n{error_details}\n\n"
        f"Пожалуйста, перегенерируйте. Убедитесь, что все гипотезы имеют непустые поля "
        f"(claim, mechanism, expected_effect каждый >= {_MIN_FIELD_LENGTH} символов) "
        f"и корректные evidence_refs, совпадающие с предоставленными chunk_id."
    )


class CandidateSynthesizer:
    def __init__(self, llm: BaseChatModel, config: MVPConfig | None = None):
        self._llm = llm
        self._config = config or MVPConfig()
        self._structured = llm.with_structured_output(HypothesisList, method="function_calling")

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
                result: HypothesisList | None = self._structured.invoke(messages)
                if result is None:
                    raise ValueError("LLM returned None from structured output")
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
