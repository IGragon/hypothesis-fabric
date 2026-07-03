from __future__ import annotations

import re

from hfabric.schemas import KPIParsed

_CHEMICAL_PATTERN = re.compile(
    r"\b(?:[A-Z][a-z]?[0-9]*)+(?:\s*\([A-Z][a-z]?\))?\b"
)
_CAPITALIZED_WORD = re.compile(r"\b[A-Z][a-z]+\b")
_PROCESS_TERMS = {
    "flotation", "leaching", "smelting", "roasting", "electrolysis",
    "cyanidation", "bioleaching", "depressant", "collector", "frother",
    "activator", "regrinding", "comminution", "classification",
    "thickening", "filtration", "calcination", "sintering",
    "amalgamation", "gravimetric", "magnetic separation",
}


def build_query_plan(kpi: KPIParsed) -> dict:
    goal = kpi.goal
    constraints = kpi.constraints

    keywords: list[str] = []
    query_text = f"query: {goal}"
    if constraints:
        query_text += " " + " ".join(constraints)

    goal_words = set(re.findall(r"\b[a-zA-Z]+\b", goal.lower()))
    constraint_words = set()
    for c in constraints:
        constraint_words.update(re.findall(r"\b[a-zA-Z]+\b", c.lower()))

    skip_words = {"the", "a", "an", "in", "on", "of", "to", "by", "with",
                  "for", "and", "or", "is", "at", "no", "be", "as", "from",
                  "that", "this", "it", "its", "not", "are", "was", "were",
                  "can", "use", "has", "have", "had", "do", "does", "did",
                  "will", "would", "could", "should", "may", "might", "into",
                  "than", "then", "also", "just", "only", "very", "too"}

    for w in goal_words | constraint_words:
        if w not in skip_words and len(w) > 1:
            keywords.append(w)

    kg_entities: list[str] = []

    goal_and_constraints = " ".join([goal] + constraints)

    chem_matches = _CHEMICAL_PATTERN.findall(goal_and_constraints)
    for cm in chem_matches:
        cm_clean = cm.strip()
        if len(cm_clean) > 1 and cm_clean.lower() not in skip_words:
            kg_entities.append(cm_clean)

    cap_matches = _CAPITALIZED_WORD.findall(goal_and_constraints)
    first_word = goal.split()[0].strip(".,;:!?")
    for cm in cap_matches:
        if cm in kg_entities:
            continue
        if cm == first_word:
            continue
        if cm.lower() in skip_words:
            continue
        kg_entities.append(cm)

    process_matches = [p for p in _PROCESS_TERMS if p.lower() in goal_and_constraints.lower()]
    for pm in process_matches:
        if pm.lower() in skip_words:
            continue
        already_present = any(pm.lower() == e.lower() for e in kg_entities)
        if not already_present:
            kg_entities.append(pm)

    return {
        "query_text": query_text,
        "keywords": sorted(keywords),
        "kg_entities": sorted(kg_entities),
    }
