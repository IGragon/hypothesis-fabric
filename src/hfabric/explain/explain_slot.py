from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field, field_validator

from hfabric.contracts import KGProtocol
from hfabric.schemas import (
    EvidenceChunk,
    ExplainedHypothesis,
    KGNode,
    ScoredHypothesis,
    TraceRecord,
)

_log = logging.getLogger("hfabric.explain")

_NARRATIVE_SECTIONS = (
    "justification",
    "uncertainty",
    "verification_plan",
    "general_approach",
    "actionable_now",
    "why_it_matters",
    "best_practices",
    "novelty",
    "risks",
)

_NO_EVIDENCE = "нет подтверждающих доказательств"
_MISSING_FIELD = "не удалось сгенерировать"

_STOPWORDS = {
    "the", "and", "for", "why", "how", "what", "this", "that",
    "with", "from", "are", "not", "has", "was", "can", "but",
    "its", "may", "due", "via",
}


class _ExplainOutput(BaseModel):
    justification: str = Field("", description="Почему гипотеза правдоподобна, со ссылками на доказательства")
    uncertainty: str = Field("", description="Пробелы, допущения, неизвестные факторы")
    verification_plan: str = Field("", description="План проверки: шаги, ресурсы, критерии успеха/неудачи")
    effect_cause_examples: list[str] = Field(default_factory=list, description="Конкретные пары 'если X, то Y'")
    general_approach: str = Field("", description="Как этот класс задач решается в целом по процитированным источникам")
    actionable_now: str = Field("", description="Что лаборатория может сделать на этой неделе")
    why_it_matters: str = Field("", description="Связь с целевым KPI и бизнес-ценностью")
    best_practices: str = Field("", description="Установленные методы/стандарты из корпуса источников")
    novelty: str = Field("", description="Насколько ново по сравнению с известными решениями")
    risks: str = Field("", description="Технические и экономические риски")

    @field_validator("effect_cause_examples", mode="before")
    @classmethod
    def _flatten_examples(cls, v):
        if v is None:
            return []
        out: list[str] = []
        for item in v:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                for key in ("example", "text", "value", "content"):
                    if key in item and isinstance(item[key], str):
                        out.append(item[key])
                        break
                else:
                    out.append(str(item))
            else:
                out.append(str(item))
        return out


_PROMPT_TEMPLATE = """Вы — аналитик-металлург. Составьте строгое, подтверждённое ссылками \
обоснование для приведённой ниже гипотезы. КАЖДЫЙ раздел ДОЛЖЕН ссылаться хотя бы на один \
элемент доказательств, используя его идентификатор в квадратных скобках в точности как показано, \
например [chunk_0007] для локального фрагмента или [web:ab12cd34] для веб-источника. \
Не выдумывайте идентификаторы. Предпочитайте цитировать веб-источники по их id, когда они \
подтверждают лучшие практики или значимость утверждений.

Целевая задача: {goal}
Целевой KPI: {metric} ({direction})

Гипотеза: {claim}
Механизм: {mechanism}
Ожидаемый эффект: {expected_effect}
Оценка: {score} (novelty={novelty}, feasibility={feasibility}, effect={effect})

Доступные доказательства (цитируйте по идентификатору в квадратных скобках):
{evidence}

Заполните КАЖДОЕ поле. Каждое поле должно содержать хотя бы одну ссылку [id] из доказательств выше. \
Если в доказательствах нет прямого подтверждения для поля, сошлитесь на ближайший релевантный \
источник и явно укажите ограничение. Все тексты пишите на русском языке.

ВАЖНО: Если структурированный вывод недоступен, ответьте ОБЫЧНЫМ ТЕКСТОМ, обернув каждое поле \
в точные XML-теги в нижнем регистре, как показано ниже (без атрибутов, без markdown-заголовков):
<justification>почему правдоподобно (2-3 предложения)</justification>
<uncertainty>пробелы/допущения (1-2 предложения)</uncertainty>
<verification_plan>конкретный план проверки — шаги, ресурсы, критерии успеха/неудачи</verification_plan>
<effect_cause_examples>
<example>2-3 конкретные пары "если X, то Y", основанные на доказательствах</example>
<example>вторая пара</example>
</effect_cause_examples>
<general_approach>как этот класс задач решается в целом по процитированным источникам</general_approach>
<actionable_now>что лаборатория может сделать НА ЭТОЙ НЕДЕЛЕ</actionable_now>
<why_it_matters>связь с целевым KPI и бизнес-ценностью</why_it_matters>
<best_practices>установленные методы/стандарты в корпусе источников</best_practices>
<novelty>насколько ново по сравнению с известными решениями</novelty>
<risks>технические и экономические риски</risks>

Содержание полей:
- justification: почему правдоподобно (2-3 предложения)
- uncertainty: пробелы/допущения (1-2 предложения)
- verification_plan: конкретный план проверки — шаги, ресурсы, критерии успеха/неудачи
- effect_cause_examples: 2-3 конкретные пары "если X, то Y", основанные на доказательствах
- general_approach: как этот класс задач решается в целом по процитированным источникам
- actionable_now: что лаборатория может сделать НА ЭТОЙ НЕДЕЛЕ
- why_it_matters: связь с целевым KPI и бизнес-ценностью
- best_practices: установленные методы/стандарты в корпусе источников
- novelty: насколько ново по сравнению с известными решениями
- risks: технические и экономические риски"""

_REPROMPT_SUFFIX = (
    "\n\nВаш предыдущий ответ оставил некоторые разделы без действительной ссылки [id]. "
    "Ответьте заново и убедитесь, что КАЖДЫЙ раздел содержит хотя бы одну ссылку [id] из доказательств выше."
)

_FALLBACK = {
    "justification": "Обоснование не было сгенерировано моделью в рамках отведённого времени.",
    "uncertainty": _MISSING_FIELD,
    "verification_plan": _MISSING_FIELD,
    "general_approach": "",
    "actionable_now": "",
    "why_it_matters": "",
    "best_practices": "",
    "novelty": "",
    "risks": "",
}

_SECTION_HEADERS = {
    "justification": ("justification", "обоснование", "почему правдоподобно", "why plausible"),
    "uncertainty": ("uncertainty", "неопределённость", "пробелы", "gaps", "assumptions"),
    "verification_plan": ("verification_plan", "verification plan", "план проверки", "roadmap", "дорожная карта"),
    "effect_cause_examples": ("effect_cause_examples", "effect cause examples", "эффект-причина", "причинно-следственные примеры"),
    "general_approach": ("general_approach", "general approach", "общий подход", "общий метод"),
    "actionable_now": ("actionable_now", "actionable now", "что делать сейчас", "что сделать на этой неделе", "what to do now"),
    "why_it_matters": ("why_it_matters", "why it matters", "почему это важно", "значимость", "value"),
    "best_practices": ("best_practices", "best practices", "лучшие практики", "установленные методы"),
    "novelty": ("novelty", "новизна", "новое"),
    "risks": ("risks", "риски", "риски:"),
}

_LIST_FIELDS = frozenset({"effect_cause_examples"})


def _extract_entity_names(text: str) -> list[str]:
    names: set[str] = set()
    for phrase in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text):
        names.add(phrase.lower())
    for sym in re.findall(r"\b[A-Z][a-z]?\b", text):
        if len(sym) >= 2:
            names.add(sym.lower())
    for w in re.findall(r"\b[a-zA-Z]{2,}\b", text):
        names.add(w.lower())
    return [n for n in names if n not in _STOPWORDS]


def _build_kg_neighbourhood(scored: ScoredHypothesis, kg: KGProtocol) -> list[str]:
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


def _valid_ids(available: dict[str, EvidenceChunk]) -> set[str]:
    ids = set(available.keys())
    for chunk in available.values():
        url = chunk.meta.get("url")
        if url:
            ids.add(url)
    return ids


def _cited_in(text: str, valid: set[str]) -> list[str]:
    found: list[str] = []
    for marker in re.findall(r"\[([^\]\n]+)\]", text or ""):
        marker = marker.strip()
        if marker in valid and marker not in found:
            found.append(marker)
    return found


def _gate_sections(data: dict, available: dict[str, EvidenceChunk]) -> tuple[dict[str, list[str]], int]:
    valid = _valid_ids(available)
    if not valid:
        return {f: [] for f in _NARRATIVE_SECTIONS}, 0
    section_citations: dict[str, list[str]] = {}
    uncovered = 0
    for field in _NARRATIVE_SECTIONS:
        value = data.get(field, "")
        text = " ".join(value) if isinstance(value, list) else str(value)
        cites = _cited_in(text, valid)
        section_citations[field] = cites
        if not cites:
            uncovered += 1
            if not text.strip() or text.strip() == _MISSING_FIELD:
                pass
            elif isinstance(value, str):
                data[field] = f"{text} ({_NO_EVIDENCE})"
    return section_citations, uncovered


_TAG_FIELDS = (
    "justification",
    "uncertainty",
    "verification_plan",
    "effect_cause_examples",
    "general_approach",
    "actionable_now",
    "why_it_matters",
    "best_practices",
    "novelty",
    "risks",
)


def _parse_tagged_sections(raw: str) -> dict[str, str | list[str]]:
    """Parse XML-style tagged sections from a free-text LLM response.

    Recognises <field>...</field> tags (case-insensitive) for every narrative
    field.  ``effect_cause_examples`` is parsed as a list of <example>...</example>
    items.  Unrecognised bare text before the first tag is treated as the
    justification (so partially-tagged responses still yield *something*).
    Returns an empty dict when no tags are present, so callers can fall back
    to the header-based parser.
    """
    out: dict[str, str | list[str]] = {}
    for field in _TAG_FIELDS:
        m = re.search(
            rf"<{field}\s*>(.*?)</{field}\s*>",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m is None:
            continue
        body = m.group(1).strip()
        if field == "effect_cause_examples":
            items = [
                it.strip()
                for it in re.findall(
                    r"<example\s*>(.*?)</example\s*>", body, flags=re.IGNORECASE | re.DOTALL
                )
                if it.strip()
            ]
            if items:
                out[field] = items
        else:
            if body:
                out[field] = body

    if not out:
        return {}

    if "justification" not in out:
        head = raw.split("<", 1)[0].strip()
        if head:
            out["justification"] = head
    return out


def _parse_free_text_sections(raw: str) -> dict[str, str | list[str]]:
    """Parse a free-text LLM response into sections by header detection.

    Recognises both English and Russian section labels, with or without
    markdown header prefixes (``#``, ``##``, ``###``).  List fields
    (``effect_cause_examples``) are returned as lists of bullet items.
    Unrecognized text before the first header is treated as the justification.
    """
    out: dict[str, str | list[str]] = {}
    current_field = "justification"
    current_buf: list[str] = []

    def _flush():
        if not current_buf:
            return
        if current_field in _LIST_FIELDS:
            items: list[str] = []
            for line in current_buf:
                stripped_line = line.strip().lstrip("-*\u2022").strip()
                if stripped_line:
                    items.append(stripped_line)
            if items and current_field not in out:
                out[current_field] = items
        else:
            text = "\n".join(current_buf).strip()
            if text and current_field not in out:
                out[current_field] = text

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            if current_buf:
                current_buf.append("")
            continue
        matched_field: str | None = None
        low = stripped.lower().rstrip(":：-").strip()
        low = re.sub(r"^#+\s*", "", low)
        for field, headers in _SECTION_HEADERS.items():
            for h in headers:
                if low.startswith(h) or low == h:
                    matched_field = field
                    break
            if matched_field:
                break
        if matched_field:
            _flush()
            current_field = matched_field
            current_buf = []
            rest = stripped.split(":", 1)[-1].strip() if ":" in stripped or "：" in stripped else ""
            if rest:
                current_buf.append(rest)
        else:
            current_buf.append(stripped)
    _flush()
    return out


class ExplainSlot:
    def __init__(
        self,
        llm: BaseChatModel,
        max_reprompt: int = 2,
        timeout_seconds: float = 90.0,
        use_structured_output: bool = True,
        workers: int = 3,
    ):
        self._llm = llm
        self._max_reprompt = max_reprompt
        self._timeout = timeout_seconds
        self._use_structured = use_structured_output
        self._workers = max(1, workers)

    def _invoke_structured(self, prompt: str) -> _ExplainOutput | None:
        import threading

        result: list = [None]
        exc: list = [None]

        def _call():
            try:
                structured = self._llm.with_structured_output(_ExplainOutput, method="function_calling")
                result[0] = structured.invoke(prompt)
            except Exception as e:
                _log.info("structured output failed (%s); trying plain invoke + section parse", e)
                try:
                    response = self._llm.invoke(prompt)
                    text = response.content if hasattr(response, "content") else str(response)
                    sections = _parse_tagged_sections(str(text))
                    if not sections:
                        sections = _parse_free_text_sections(str(text))
                    ece = sections.get("effect_cause_examples", [])
                    if isinstance(ece, str):
                        ece = [l.strip().lstrip("-*\u2022").strip() for l in ece.split("\n") if l.strip()]
                    result[0] = _ExplainOutput(
                        justification=sections.get("justification", str(text)[:2000]),
                        uncertainty=sections.get("uncertainty", ""),
                        verification_plan=sections.get("verification_plan", ""),
                        effect_cause_examples=ece if isinstance(ece, list) else [],
                        general_approach=sections.get("general_approach", ""),
                        actionable_now=sections.get("actionable_now", ""),
                        why_it_matters=sections.get("why_it_matters", ""),
                        best_practices=sections.get("best_practices", ""),
                        novelty=sections.get("novelty", ""),
                        risks=sections.get("risks", ""),
                    )
                except Exception as e2:
                    exc[0] = e2

        thread = threading.Thread(target=_call, daemon=True)
        thread.start()
        thread.join(timeout=self._timeout)
        if thread.is_alive():
            _log.warning("explain LLM timed out after %.0fs", self._timeout)
            return None
        if exc[0] is not None and result[0] is None:
            _log.warning("explain LLM both paths failed: %s", exc[0])
            return None
        return result[0]

    def explain(
        self,
        ranked: list[ScoredHypothesis],
        evidence_map: dict[str, EvidenceChunk] | list[EvidenceChunk],
        kg: KGProtocol,
        trace: TraceRecord | None = None,
        external: list[EvidenceChunk] | None = None,
    ) -> list[ExplainedHypothesis]:
        if isinstance(evidence_map, dict):
            evidence_list = list(evidence_map.values())
        else:
            evidence_list = evidence_map
        external = external or []

        t0 = time.time()
        n = len(ranked)

        def _one(idx_scored: tuple[int, ScoredHypothesis]) -> tuple[int, ExplainedHypothesis, int, int]:
            idx, scored = idx_scored
            neighbourhood_lines = _build_kg_neighbourhood(scored, kg)

            available: dict[str, EvidenceChunk] = dict(scored.cited_refs)
            for ext in external:
                available[ext.chunk_id] = ext

            evidence_block = "\n".join(
                f"[{cid}] {chunk.meta.get('url', '') and '(web) ' or ''}{chunk.text[:400]}"
                for cid, chunk in available.items()
            ) or "(нет доказательств)"

            hyp = scored.hypothesis
            features = scored.features
            prompt = _PROMPT_TEMPLATE.format(
                goal=hyp.claim,
                metric=features.get("metric", "целевой KPI"),
                direction=str(features.get("direction", "") or ""),
                claim=hyp.claim,
                mechanism=hyp.mechanism,
                expected_effect=hyp.expected_effect,
                score=scored.score,
                novelty=features.get("novelty", 0.0),
                feasibility=features.get("feasibility", 0.0),
                effect=features.get("effect", 0.0),
                evidence=evidence_block,
            )

            token_in = len(prompt)
            token_out = 0
            data = dict(_FALLBACK)
            data["effect_cause_examples"] = []

            if not self._use_structured:
                output = None
            else:
                output = self._invoke_structured(prompt)
            if output is None:
                if self._use_structured:
                    _log.info("hyp %d/%d: structured failed/timed out, falling back to plain invoke", idx, n)
                else:
                    _log.info("hyp %d/%d: plain invoke (structured disabled)", idx, n)
                try:
                    response = self._llm.invoke(prompt)
                    text = response.content if hasattr(response, "content") else str(response)
                    sections = _parse_tagged_sections(str(text))
                    if not sections:
                        sections = _parse_free_text_sections(str(text))
                    ece_raw = sections.pop("effect_cause_examples", None)
                    data.update(sections)
                    if isinstance(ece_raw, list) and ece_raw:
                        data["effect_cause_examples"] = ece_raw
                    data.setdefault("justification", str(text)[:2000])
                    token_out = len(str(text))
                except Exception as e:
                    _log.warning("hyp %d/%d: plain invoke also failed: %s", idx, n, e)
            else:
                data = output.model_dump()
                token_out = len(str(data))

            section_citations: dict[str, list[str]] = {}
            attempts = 0
            while True:
                section_citations, uncovered = _gate_sections(data, available)
                if uncovered == 0 or attempts >= self._max_reprompt:
                    break
                if output is None:
                    break
                attempts += 1
                _log.info(
                    "hyp %d/%d: %d sections uncovered, re-prompt %d/%d",
                    idx, n, uncovered, attempts, self._max_reprompt,
                )
                retry = self._invoke_structured(prompt + _REPROMPT_SUFFIX)
                if retry is None:
                    break
                data = retry.model_dump()

            cited_ids: set[str] = set()
            for cites in section_citations.values():
                cited_ids.update(cites)

            merged_refs = dict(scored.cited_refs)
            external_urls: list[str] = []
            for chunk in available.values():
                url = chunk.meta.get("url")
                is_cited = chunk.chunk_id in cited_ids or (url and url in cited_ids)
                if is_cited and chunk.chunk_id not in merged_refs:
                    merged_refs[chunk.chunk_id] = chunk
                if is_cited and url:
                    external_urls.append(url)

            scored_copy = ScoredHypothesis(
                hypothesis=scored.hypothesis,
                score=scored.score,
                features=scored.features,
                cited_refs=merged_refs,
            )

            filled = sum(1 for f in _NARRATIVE_SECTIONS if str(data.get(f, "")).strip())
            _log.info(
                "hyp %d/%d: %s — %d/9 narrative fields filled, %d external urls cited",
                idx, n, hyp.claim[:50], filled, len(external_urls),
            )

            eh = ExplainedHypothesis(
                scored=scored_copy,
                justification=str(data.get("justification") or _FALLBACK["justification"]),
                uncertainty=str(data.get("uncertainty") or _FALLBACK["uncertainty"]),
                verification_plan=str(data.get("verification_plan") or _FALLBACK["verification_plan"]),
                graph_neighbourhood=neighbourhood_lines,
                effect_cause_examples=list(data.get("effect_cause_examples") or []),
                general_approach=str(data.get("general_approach") or ""),
                actionable_now=str(data.get("actionable_now") or ""),
                why_it_matters=str(data.get("why_it_matters") or ""),
                best_practices=str(data.get("best_practices") or ""),
                novelty=str(data.get("novelty") or ""),
                risks=str(data.get("risks") or ""),
                section_citations=section_citations,
                external_urls=list(dict.fromkeys(external_urls)),
            )
            return idx, eh, token_in, token_out

        workers = min(self._workers, n) if n > 0 else 1
        results: list[ExplainedHypothesis] = [None] * n  # type: ignore[list-item]
        total_in = 0
        total_out = 0
        if workers <= 1 or n <= 1:
            for item in enumerate(ranked, 1):
                idx, eh, ti, to = _one(item)
                results[idx - 1] = eh
                total_in += ti
                total_out += to
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="explain") as pool:
                futures = [pool.submit(_one, item) for item in enumerate(ranked, 1)]
                for fut in futures:
                    idx, eh, ti, to = fut.result()
                    results[idx - 1] = eh
                    total_in += ti
                    total_out += to

        if trace is not None:
            trace.token_in += total_in
            trace.token_out += total_out

        latency_ms = (time.time() - t0) * 1000
        if trace is not None:
            trace.latency_ms += latency_ms

        return results
