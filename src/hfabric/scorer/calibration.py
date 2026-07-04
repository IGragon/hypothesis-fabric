from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hfabric.storage.feedback_store import FeedbackStore


def apply_feedback_weights(
    feedback_store: FeedbackStore | None,
    current_weights: dict[str, float],
) -> dict[str, float]:
    if feedback_store is None:
        return dict(current_weights)
    try:
        labels = feedback_store.get_all_labels()
    except Exception:
        return dict(current_weights)
    if not labels:
        return dict(current_weights)
    calibrator = WeightCalibrator()
    return calibrator.calibrate(labels, current_weights)


class WeightCalibrator:
    def __init__(self, step: float = 0.05, max_iterations: int = 100) -> None:
        self._step = step
        self._max_iterations = max_iterations

    def calibrate(
        self,
        labels: list[dict],
        current_weights: dict[str, float],
    ) -> dict[str, float]:
        if not labels:
            return dict(current_weights)

        clean = self._exclude_conflicts(labels)

        if not clean:
            return dict(current_weights)

        accepted_claims = {
            label["hypothesis_claim"]
            for label in clean
            if label["label"] == "accepted"
        }
        rejected_claims = {
            label["hypothesis_claim"]
            for label in clean
            if label["label"] == "rejected"
        }

        if not accepted_claims and not rejected_claims:
            return dict(current_weights)

        weights = dict(current_weights)
        weight_keys = sorted(weights.keys())
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        else:
            n = len(weight_keys)
            weights = {k: 1.0 / n for k in weight_keys}

        best_weights = dict(weights)
        best_score = 0.0

        for _ in range(self._max_iterations):
            improved = False
            for k in weight_keys:
                new_weights = dict(weights)
                new_weights[k] = min(1.0, weights[k] + self._step)
                self._normalize(new_weights)

                score = self._evaluate(new_weights, clean, accepted_claims, rejected_claims)
                if score > best_score:
                    best_score = score
                    best_weights = dict(new_weights)
                    weights = new_weights
                    improved = True

                new_weights = dict(weights)
                new_weights[k] = max(0.0, weights[k] - self._step)
                self._normalize(new_weights)

                score = self._evaluate(new_weights, clean, accepted_claims, rejected_claims)
                if score > best_score:
                    best_score = score
                    best_weights = dict(new_weights)
                    weights = new_weights
                    improved = True

            if not improved:
                break

        return self._check_bounds(best_weights)

    def _exclude_conflicts(self, labels: list[dict]) -> list[dict]:
        claim_labels: dict[str, set[str]] = {}
        for label in labels:
            claim = label["hypothesis_claim"]
            if claim not in claim_labels:
                claim_labels[claim] = set()
            claim_labels[claim].add(label["label"])

        conflicting = {c for c, ls in claim_labels.items() if len(ls) > 1}
        return [l for l in labels if l["hypothesis_claim"] not in conflicting]

    def _evaluate(
        self,
        weights: dict[str, float],
        labels: list[dict],
        accepted_claims: set[str],
        rejected_claims: set[str],
    ) -> float:
        score = 0.0
        for label in labels:
            claim = label["hypothesis_claim"]
            features = label.get("features", {"novelty": 0.5, "feasibility": 0.5, "effect": 0.5})
            weighted = sum(
                weights.get(k, 0.0) * features.get(k, 0.0)
                for k in weights
            )

            if claim in accepted_claims:
                score += weighted
            elif claim in rejected_claims:
                score += (1.0 - weighted)

        return score / len(labels) if labels else 0.0

    def _normalize(self, weights: dict[str, float]) -> None:
        total = sum(weights.values())
        if total > 0:
            for k in weights:
                weights[k] /= total

    def _check_bounds(self, weights: dict[str, float]) -> dict[str, float]:
        result = {}
        for k, v in weights.items():
            result[k] = max(0.0, min(1.0, v))
        total = sum(result.values())
        if total > 0:
            for k in result:
                result[k] /= total
        return result
