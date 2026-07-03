from __future__ import annotations

import json
import os

from rapidfuzz import fuzz

from hfabric.schemas import Hypothesis


def load_golden_hypotheses(path: str | None = None) -> list[dict]:
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "golden_hypotheses.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def match_golden(
    candidates: list[Hypothesis],
    golden: list[dict] | None = None,
    threshold: int = 60,
) -> dict:
    if golden is None:
        golden = load_golden_hypotheses()

    matches: list[dict] = []
    best_score = 0

    for g in golden:
        g_claim = g["claim"]
        g_keywords = set(k.lower() for k in g.get("keywords", []))

        best_candidate = None
        best_ratio = 0

        for cand in candidates:
            ratio = fuzz.token_sort_ratio(g_claim.lower(), cand.claim.lower())

            cand_text = (cand.claim + " " + cand.mechanism + " " + cand.expected_effect).lower()
            keyword_hits = sum(1 for kw in g_keywords if kw in cand_text)
            keyword_score = keyword_hits / len(g_keywords) if g_keywords else 0

            combined = ratio * 0.6 + keyword_score * 100 * 0.4

            if combined > best_ratio:
                best_ratio = combined
                best_candidate = cand

        if best_candidate is not None and best_ratio >= threshold:
            matches.append({
                "golden_claim": g_claim,
                "matched_claim": best_candidate.claim,
                "score": best_ratio,
            })
            if best_ratio > best_score:
                best_score = best_ratio

    return {
        "matched_count": len(matches),
        "total_golden": len(golden),
        "passed": len(matches) >= 1,
        "matches": matches,
        "best_score": best_score,
    }
