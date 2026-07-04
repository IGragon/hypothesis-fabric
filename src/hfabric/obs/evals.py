from __future__ import annotations

from rapidfuzz import fuzz

from hfabric.schemas import Hypothesis, ScoredHypothesis


def _get_hypothesis(item: Hypothesis | ScoredHypothesis) -> Hypothesis:
    if isinstance(item, ScoredHypothesis):
        return item.hypothesis
    return item


def jaccard_at_10(
    run_a: list[Hypothesis], run_b: list[Hypothesis]
) -> float:
    def _top10(hs: list[Hypothesis]) -> list[Hypothesis]:
        if not hs:
            return []
        scored = [
            (
                h,
                getattr(h, "score", 0.0)
                if hasattr(h, "score")
                else 0.0,
            )
            for h in hs
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [h for h, _ in scored[:10]]

    a_top = _top10(run_a)
    b_top = _top10(run_b)

    if not a_top and not b_top:
        return 1.0
    if not a_top or not b_top:
        return 0.0

    threshold = 80
    matched_b = [False] * len(b_top)
    intersection = 0

    for ha in a_top:
        for j, hb in enumerate(b_top):
            if not matched_b[j]:
                ratio = fuzz.token_sort_ratio(ha.claim, hb.claim)
                if ratio >= threshold:
                    intersection += 1
                    matched_b[j] = True
                    break

    union = len(a_top) + len(b_top) - intersection
    return intersection / union if union > 0 else 0.0


def schema_validity_check(
    hypotheses: list[Hypothesis] | list[ScoredHypothesis],
) -> dict:
    violations: list[str] = []
    for i, item in enumerate(hypotheses):
        h = _get_hypothesis(item)
        prefix = f"Hypothesis[{i}]"
        if not h.claim or len(h.claim) <= 10:
            violations.append(f"{prefix}: claim empty or <= 10 chars")
        if not h.mechanism or len(h.mechanism) <= 10:
            violations.append(f"{prefix}: mechanism empty or <= 10 chars")
        if not h.expected_effect:
            violations.append(f"{prefix}: expected_effect empty")
        if not h.evidence_refs:
            violations.append(f"{prefix}: evidence_refs empty")

    return {
        "passed": len(violations) == 0,
        "failed_count": len({v.split(":")[0] for v in violations}),
        "violations": violations,
    }


def citation_existence_check(
    hypotheses: list[ScoredHypothesis],
) -> dict:
    total_refs = 0
    matched_refs = 0

    for sh in hypotheses:
        for ref in sh.hypothesis.evidence_refs:
            total_refs += 1
            if ref in sh.cited_refs:
                matched_refs += 1

    coverage = matched_refs / total_refs if total_refs > 0 else 0.0
    return {
        "passed": total_refs == 0 or coverage >= 1.0,
        "total_refs": total_refs,
        "matched_refs": matched_refs,
        "coverage": coverage,
    }


def constraint_pass_check(
    hypotheses: list[Hypothesis] | list[ScoredHypothesis],
    constraints: list[str],
) -> dict:
    from hfabric.scorer.constraint import constraint_check

    total = len(hypotheses)
    pass_count = 0
    for item in hypotheses:
        h = _get_hypothesis(item)
        result = constraint_check(h, constraints)
        if result["ok"]:
            pass_count += 1

    return {
        "passed": pass_count == total and total > 0,
        "pass_count": pass_count,
        "total": total,
        "pass_rate": pass_count / total if total > 0 else 0.0,
    }


def run_evals(
    session_id: str,
    hypotheses: list[Hypothesis] | list[ScoredHypothesis],
    constraints: list[str] | None = None,
) -> dict:
    result: dict = {
        "session_id": session_id,
        "schema_validity": schema_validity_check(hypotheses),
    }

    if hypotheses and isinstance(hypotheses[0], ScoredHypothesis):
        result["citation_existence"] = citation_existence_check(hypotheses)

    if constraints is not None:
        result["constraint_pass"] = constraint_pass_check(hypotheses, constraints)

    return result
