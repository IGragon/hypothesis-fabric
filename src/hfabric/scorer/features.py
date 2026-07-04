from __future__ import annotations

import re
from typing import TYPE_CHECKING

from hfabric.scorer.constraint import (
    constraint_check,
    constraint_satisfied,
    negation_violated,
    get_topical_keywords,
    is_negation_constraint,
    _is_equipment_availability,
)

if TYPE_CHECKING:
    from hfabric.contracts import KGProtocol
    from hfabric.schemas import Hypothesis, KPIParsed

_ENTITY_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
_CHEM_RE = re.compile(r"\b[A-Z][a-z]?\b")
_TOK_RE = re.compile(r"\w+")


def _tokenize(text: str) -> set[str]:
    return set(t.lower() for t in _TOK_RE.findall(text))


def _find_entities(text: str) -> set[str]:
    caps = set(_ENTITY_RE.findall(text))
    chems = set(_CHEM_RE.findall(text))
    all_terms = caps | chems
    stop = {
        "The", "This", "In", "At", "By", "To", "Of", "On", "For", "An", "As",
        "We", "He", "It", "Is", "Be", "No", "So", "Or", "If", "Do", "Go",
    }
    return {t for t in all_terms if t not in stop}


def extract_novelty(hypothesis: Hypothesis, kg: KGProtocol) -> float:
    text = hypothesis.claim + " " + hypothesis.mechanism
    entities = _find_entities(text)

    if not entities or kg is None:
        return 0.5

    neighbour_counts: list[int] = []
    for name in entities:
        try:
            kg_entities = kg.get_entities(name)
        except Exception:
            continue
        if not kg_entities:
            continue
        for kg_ent in kg_entities:
            try:
                neighbours = kg.neighbours(kg_ent.id, hops=2)
                neighbour_counts.append(len(neighbours))
            except Exception:
                continue

    if not neighbour_counts:
        return 0.5

    avg_neighbours = sum(neighbour_counts) / len(neighbour_counts)
    novelty = 1.0 - min(1.0, avg_neighbours / 10.0)
    return max(0.0, min(1.0, novelty))


def extract_feasibility(hypothesis: Hypothesis, constraints: list[str]) -> float:
    if not constraints:
        return 1.0

    satisfied = 0
    for constraint in constraints:
        if constraint_satisfied(hypothesis, constraint):
            satisfied += 1

    return satisfied / len(constraints)


def extract_risk(hypothesis: Hypothesis, kg: KGProtocol | None = None) -> float:
    claim = hypothesis.claim.lower()
    risk_keywords = {
        "cyanide": 0.8,
        "cyanid": 0.8,
        "цианид": 0.8,
        "toxic": 0.7,
        "токсич": 0.7,
        "expensive": 0.6,
        "дорог": 0.6,
        "химический реагент": 0.5,
        "environmental": 0.7,
        "экологич": 0.7,
        "hazardous": 0.8,
        "опасн": 0.7,
        "waste": 0.5,
        "отход": 0.5,
        "pressure": 0.4,
        "давление": 0.4,
        "high temperature": 0.4,
        "высокая температура": 0.4,
    }
    score = 0.0
    matched = 0
    for kw, risk in risk_keywords.items():
        if kw in claim:
            score = max(score, risk)
            matched += 1

    if matched == 0:
        return 0.2
    return score


def extract_realizability(hypothesis: Hypothesis, constraints: list[str]) -> float:
    claim = hypothesis.claim.lower()

    if not constraints:
        return 0.8

    feasibility_keywords = {
        "simple": 0.9, "standard": 0.8, "existing": 0.7,
        "простой": 0.9, "стандартный": 0.8, "существующий": 0.7,
        "modify": 0.7, "adjust": 0.7, "fine-tune": 0.8,
        "модифицировать": 0.7, "настроить": 0.8, "регулировать": 0.7,
    }

    base = 0.6
    for kw, boost in feasibility_keywords.items():
        if kw in claim:
            base = max(base, boost)

    constraint_violations = 0
    for const in constraints:
        const_lower = const.lower()
        if is_negation_constraint(const_lower):
            keywords = get_topical_keywords(const_lower)
            if negation_violated(hypothesis.claim + " " + hypothesis.mechanism, keywords):
                constraint_violations += 1
        elif _is_equipment_availability(const_lower):
            if not constraint_satisfied(hypothesis, const):
                constraint_violations += 1

    if constraint_violations > 0:
        base -= 0.3 * constraint_violations

    return max(0.1, min(1.0, base))


def extract_effect(hypothesis: Hypothesis, kpi: KPIParsed) -> float:
    kpi_text = f"{kpi.kpi.metric} {kpi.kpi.target or ''} {kpi.goal}"
    kpi_tokens = _tokenize(kpi_text)
    effect_tokens = _tokenize(hypothesis.expected_effect)

    if not kpi_tokens:
        return 0.5

    overlap = kpi_tokens & effect_tokens
    score = len(overlap) / len(kpi_tokens)

    effect_lower = hypothesis.expected_effect.lower()
    if kpi.kpi.direction == "increase":
        inc_words = ["increase", "improve", "higher", "boost", "raise", "enhance", "+"]
        if any(w in effect_lower for w in inc_words):
            score = min(1.0, score + 0.2)
    elif kpi.kpi.direction == "decrease":
        dec_words = ["decrease", "reduce", "lower", "less", "drop", "-"]
        if any(w in effect_lower for w in dec_words):
            score = min(1.0, score + 0.2)

    return max(0.0, min(1.0, score))
