from __future__ import annotations

import logging

from hfabric.schemas import Hypothesis, ScoredHypothesis

_log = logging.getLogger("hfabric.scorer")

_DEFAULT_WEIGHTS: dict[str, float] = {
    "novelty": 0.20,
    "feasibility": 0.25,
    "effect": 0.20,
    "risk": 0.10,
    "realizability": 0.10,
    "evidence": 0.10,
    "violation": 0.15,
}


class WeightedRanker:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights if weights is not None else dict(_DEFAULT_WEIGHTS)

    def rank(self, hypotheses: list[dict]) -> list[ScoredHypothesis]:
        scored: list[ScoredHypothesis] = []
        for entry in hypotheses:
            hyp: Hypothesis = entry["hypothesis"]
            features: dict[str, float] = entry["features"]
            base = (
                self.weights.get("novelty", 0.0) * features.get("novelty", 0.0)
                + self.weights.get("feasibility", 0.0) * features.get("feasibility", 0.0)
                + self.weights.get("effect", 0.0) * features.get("effect", 0.0)
                + self.weights.get("realizability", 0.0) * features.get("realizability", 0.0)
                + self.weights.get("risk", 0.0) * (1.0 - features.get("risk", 0.5))
            )

            evidence_count = features.get("evidence_count", 0.0)
            evidence_term = self.weights.get("evidence", 0.0) * (1.0 - 1.0 / (1.0 + evidence_count))
            base += evidence_term

            violations = features.get("violation_count", 0.0)
            violation_penalty = self.weights.get("violation", 0.0) * violations
            base -= violation_penalty

            gate = max(0.3, 1.0 - 0.3 * violations)
            score = base * gate

            scored.append(
                ScoredHypothesis(
                    hypothesis=hyp,
                    score=score,
                    features=features,
                    cited_refs={},
                )
            )

        scored.sort(key=lambda s: (-s.score, hash(s.hypothesis.claim)))
        if _log.isEnabledFor(logging.DEBUG):
            for s in scored:
                _log.debug(
                    "rank: %s score=%.3f ev=%s viol=%s feas=%.2f",
                    s.hypothesis.claim[:40], s.score,
                    s.features.get("evidence_count", 0), s.features.get("violation_count", 0),
                    s.features.get("feasibility", 0),
                )
        return scored
