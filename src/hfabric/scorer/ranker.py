from __future__ import annotations

from hfabric.schemas import Hypothesis, ScoredHypothesis

_DEFAULT_WEIGHTS: dict[str, float] = {
    "novelty": 0.3,
    "feasibility": 0.4,
    "effect": 0.3,
}


class WeightedRanker:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights if weights is not None else dict(_DEFAULT_WEIGHTS)

    def rank(self, hypotheses: list[dict]) -> list[ScoredHypothesis]:
        scored: list[ScoredHypothesis] = []
        for entry in hypotheses:
            hyp: Hypothesis = entry["hypothesis"]
            features: dict[str, float] = entry["features"]
            score = (
                self.weights.get("novelty", 0.0) * features.get("novelty", 0.0)
                + self.weights.get("feasibility", 0.0) * features.get("feasibility", 0.0)
                + self.weights.get("effect", 0.0) * features.get("effect", 0.0)
            )
            scored.append(
                ScoredHypothesis(
                    hypothesis=hyp,
                    score=score,
                    features=features,
                    cited_refs={},
                )
            )

        scored.sort(key=lambda s: (-s.score, hash(s.hypothesis.claim)))
        return scored
