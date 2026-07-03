from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hfabric.contracts import KGProtocol
    from hfabric.schemas import Hypothesis, KPIParsed

_ENTITY_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
_CHEM_RE = re.compile(r"\b[A-Z][a-z]?\b")
_TOK_RE = re.compile(r"\w+")

_NEGATION_WORDS = {
    "no", "not", "without", "avoid", "prevent",
    "reduce", "decrease", "lower", "less",
}
_POSITIVE_INDICATORS = {
    "increase", "improve", "enhance", "raise", "boost",
    "higher", "more", "add", "+",
}
_ACTION_WORDS = _POSITIVE_INDICATORS | {
    "use", "apply", "utilize", "employ", "decrease",
    "reduce", "lower", "less", "drop",
}


def _tokenize(text: str) -> set[str]:
    return set(t.lower() for t in _TOK_RE.findall(text))


def _get_topical_keywords(constraint_lower: str) -> list[str]:
    all_tokens = _TOK_RE.findall(constraint_lower)
    return [t for t in all_tokens if t not in _ACTION_WORDS and t not in _NEGATION_WORDS and (len(t) > 2 or (len(t) == 2 and t[0].isupper()))]


def _find_entities(text: str) -> set[str]:
    caps = set(_ENTITY_RE.findall(text))
    chems = set(_CHEM_RE.findall(text))
    all_terms = caps | chems
    stop = {
        "The", "This", "In", "At", "By", "To", "Of", "On", "For", "An", "As",
        "We", "He", "It", "Is", "Be", "No", "So", "Or", "If", "Do", "Go",
    }
    return {t for t in all_terms if t not in stop}


def _is_negation_constraint(constraint_lower: str) -> bool:
    return any(
        constraint_lower.startswith(w) or f" {w} " in f" {constraint_lower} "
        for w in _NEGATION_WORDS
    )


def _negation_violated(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    for kw in keywords:
        kw_lower = kw.lower()
        idx = text_lower.find(kw_lower)
        while idx != -1:
            window_start = max(0, idx - 50)
            window_end = min(len(text_lower), idx + len(kw_lower) + 50)
            window = text_lower[window_start:window_end]

            has_negation = any(w in window for w in _NEGATION_WORDS)
            has_positive = any(w in window for w in _POSITIVE_INDICATORS)

            if has_positive and not has_negation:
                return True

            idx = text_lower.find(kw_lower, idx + 1)

    return False


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

    text = hypothesis.claim + " " + hypothesis.mechanism + " " + hypothesis.expected_effect

    satisfied = 0
    for constraint in constraints:
        constraint_lower = constraint.lower()
        keywords = _get_topical_keywords(constraint_lower)

        if _is_negation_constraint(constraint_lower):
            if not _negation_violated(text, keywords):
                satisfied += 1
        else:
            text_lower = text.lower()
            if not keywords or all(kw.lower() in text_lower for kw in keywords):
                satisfied += 1

    return satisfied / len(constraints)


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
