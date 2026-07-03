from __future__ import annotations

import re

from hfabric.schemas import Hypothesis

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
    return [
        t for t in all_tokens
        if t not in _ACTION_WORDS
        and t not in _NEGATION_WORDS
        and (len(t) > 2 or (len(t) == 2 and t[0].isupper()))
    ]


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


def constraint_check(hypothesis: Hypothesis, constraints: list[str]) -> dict:
    text = hypothesis.claim + " " + hypothesis.mechanism + " " + hypothesis.expected_effect
    text_lower = text.lower()
    violations: list[str] = []

    for constraint in constraints:
        constraint_lower = constraint.lower()
        keywords = _get_topical_keywords(constraint_lower)

        if _is_negation_constraint(constraint_lower):
            if _negation_violated(text, keywords):
                violations.append(
                    f"Constraint '{constraint}' violated: keyword(s) found in positive context"
                )
        else:
            for kw in keywords:
                if kw.lower() not in text_lower:
                    violations.append(
                        f"Constraint '{constraint}' requires keyword '{kw}' not found in hypothesis"
                    )

    return {"ok": len(violations) == 0, "violations": violations}
