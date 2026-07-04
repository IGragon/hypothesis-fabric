from __future__ import annotations

import re

from hfabric.schemas import Hypothesis

_TOK_RE = re.compile(r"\w+")

_NEGATION_WORDS = {
    "no", "not", "without", "avoid", "prevent",
    "reduce", "decrease", "lower", "less",
    "без", "не", "нельзя", "избегать", "предотвращать",
    "снизить", "уменьшить", "ограничен",
}
_POSITIVE_INDICATORS = {
    "increase", "improve", "enhance", "raise", "boost",
    "higher", "more", "add", "+",
    "увеличить", "повысить", "улучшить", "добавить", "больше",
}
_ACTION_WORDS = _POSITIVE_INDICATORS | {
    "use", "apply", "utilize", "employ", "decrease",
    "reduce", "lower", "less", "drop",
    "must", "should", "shall", "needs", "need", "require", "requires",
    "использовать", "применять", "должен", "нужно", "требует",
}


def _tokenize(text: str) -> set[str]:
    return set(t.lower() for t in _TOK_RE.findall(text))


def get_topical_keywords(constraint_lower: str) -> list[str]:
    all_tokens = _TOK_RE.findall(constraint_lower)
    return [
        t for t in all_tokens
        if t not in _ACTION_WORDS
        and t not in _NEGATION_WORDS
        and (len(t) > 2 or (len(t) == 2 and t[0].isupper()))
    ]


def is_negation_constraint(constraint_lower: str) -> bool:
    return any(
        constraint_lower.startswith(w) or f" {w} " in f" {constraint_lower} "
        for w in _NEGATION_WORDS
    )


_KNOWN_EQUIPMENT = {
    "мельниц", "мельница", "мельницы", "мельницу", "мельницей",
    "гидроциклон", "гидроциклоны", "гидроциклона", "гидроциклонов",
    "контактный чан", "контактные чаны", "контактного чана", "контактных чанов",
    "флотомашин", "флотомашина", "флотомашины", "флотомашину",
    "сепаратор", "сепараторы", "сепаратора", "сепараторов",
    "магнитный сепаратор", "магнитного сепаратора", "магнитные сепараторы",
    "магнитн", "магнитная сепарация", "магнитной сепарации",
    "печ", "печь", "печи", "печи обжига", "обжиговая печь",
    "пресс", "прессы", "пресса", "прессование", "брикетировочный пресс",
    "грохот", "грохоты", "грохота",
    "фильтр", "фильтры", "фильтра", "вакуум-фильтр",
    "сгуститель", "сгустители", "сгустителя",
    "классификатор", "классификаторы",
    "мельница полусамоизмельчения", "mse", "sag",
    "шаровая мельница", "шаровой мельницы", "стержневая мельница",
    "magnetic separator", "kiln", "press", "screen", "filter", "thickener",
    "classifier", "ball mill", "sag mill", "rod mill", "flotation cell",
}

_EQUIPMENT_AVAILABLE_MARKERS = ("доступное оборудование", "доступные оборудование",
    "available equipment", "имеющееся оборудование", "в наличии оборудование",
    "оборудование:", "equipment:",
    "схема включает", "текущая схема", "действующая схема",
    "current scheme", "схема состоит", "включает",
)

_BUDGET_MARKERS = ("бюджет", "budget", "cost", "стоимость", "капитальные затраты", "capex", "opex")

_NORMATIVE_MARKERS = ("норматив", "norm", "regulation", "стандарт", "пдк", "limit")

_SOFT_MARKERS = (
    "приоритет", "предпочтение", "priority", "preference",
    "желательно", "preferably", "рекомендуется", "recommended",
)


def is_availability_constraint(constraint_lower: str) -> bool:
    generic = ("доступное", "доступные", "available", "имеется", "в наличии")
    return (
        any(m in constraint_lower for m in generic)
        or any(m in constraint_lower for m in (_BUDGET_MARKERS + _NORMATIVE_MARKERS + _EQUIPMENT_AVAILABLE_MARKERS))
    )


def _is_equipment_availability(constraint_lower: str) -> bool:
    return any(m in constraint_lower for m in _EQUIPMENT_AVAILABLE_MARKERS)


def _parse_allowed_equipment(constraint: str) -> set[str]:
    """Extract the allowed-equipment noun set from a constraint like
    'Доступное оборудование: мельницы, гидроциклоны, контактные чаны'."""
    lower = constraint.lower()
    sep_idx = -1
    for marker in _EQUIPMENT_AVAILABLE_MARKERS:
        idx = lower.find(marker)
        if idx != -1:
            sep_idx = idx + len(marker)
            break
    if sep_idx == -1:
        return set()
    rest = constraint[sep_idx:].lstrip(":;, \t")
    tokens = re.split(r"[,;]\s*", rest)
    allowed: set[str] = set()
    for tok in tokens:
        tok = tok.strip().rstrip(".")
        if not tok:
            continue
        allowed.add(tok.lower())
        for word in re.findall(r"\w+", tok.lower()):
            if len(word) > 2:
                allowed.add(word)
    return allowed


def _detect_equipment_in_text(text: str) -> set[str]:
    """Detect equipment nouns mentioned in the hypothesis text that are
    known, separate pieces of equipment (not generic process terms)."""
    text_lower = text.lower()
    found: set[str] = set()
    for eq in _KNOWN_EQUIPMENT:
        if eq in text_lower:
            found.add(eq)
    return found


def _stem(word: str, n: int = 6) -> str:
    return word[:min(len(word), n)].lower()


def _equipment_violation(text: str, allowed: set[str]) -> bool:
    detected = _detect_equipment_in_text(text)
    if not detected:
        return False
    allowed_stems = {_stem(aw) for aw in allowed if len(aw) >= 3}
    for eq in detected:
        if eq in allowed:
            continue
        eq_stem = _stem(eq)
        if eq_stem in allowed_stems:
            continue
        for aw in allowed:
            if eq in aw or aw in eq:
                break
            if len(aw) >= 4 and len(eq) >= 4 and (eq.startswith(aw[:4]) or aw.startswith(eq[:4])):
                break
        else:
            return True
    return False


def negation_violated(text: str, keywords: list[str]) -> bool:
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


def positive_satisfied(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text_lower = text.lower()
    return all(kw.lower() in text_lower for kw in keywords)


def _is_soft_constraint(constraint_lower: str) -> bool:
    return any(m in constraint_lower for m in _SOFT_MARKERS)


def constraint_satisfied(hypothesis: Hypothesis, constraint: str) -> bool:
    text = (
        hypothesis.claim + " " + hypothesis.mechanism
        + " " + hypothesis.expected_effect
    )
    constraint_lower = constraint.lower()

    if _is_soft_constraint(constraint_lower):
        return True

    if _is_equipment_availability(constraint_lower):
        allowed = _parse_allowed_equipment(constraint)
        if allowed and _equipment_violation(text, allowed):
            return False
        return True

    if is_availability_constraint(constraint_lower):
        return True

    keywords = get_topical_keywords(constraint_lower)
    if is_negation_constraint(constraint_lower):
        return not negation_violated(text, keywords)
    return positive_satisfied(text, keywords)


def constraint_check(hypothesis: Hypothesis, constraints: list[str]) -> dict:
    violations: list[str] = []
    for constraint in constraints:
        if not constraint_satisfied(hypothesis, constraint):
            constraint_lower = constraint.lower()
            if _is_equipment_availability(constraint_lower):
                reason = "использовано оборудование, не входящее в список доступного"
            elif is_negation_constraint(constraint_lower):
                reason = "keyword(s) found in positive context"
            else:
                reason = "required keyword(s) missing"
            violations.append(
                f"Constraint '{constraint}' violated: {reason}"
            )

    return {"ok": len(violations) == 0, "violations": violations}