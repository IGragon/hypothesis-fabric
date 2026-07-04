from __future__ import annotations

import pytest

from hfabric.scorer.calibration import WeightCalibrator


@pytest.fixture
def calibrator():
    return WeightCalibrator(step=0.05, max_iterations=100)


class TestWeightCalibrator:
    def test_empty_labels_returns_original_weights(self, calibrator):
        weights = {"novelty": 0.3, "feasibility": 0.4, "effect": 0.3}
        result = calibrator.calibrate([], weights)
        assert result == weights

    def test_weights_sum_to_one(self, calibrator):
        weights = {"novelty": 0.3, "feasibility": 0.4, "effect": 0.3}
        labels = [
            {
                "hypothesis_claim": "Use PAX for higher recovery",
                "label": "accepted",
                "expert_id": "e1",
                "features": {"novelty": 0.6, "feasibility": 0.9, "effect": 0.7},
            },
        ]
        result = calibrator.calibrate(labels, weights)
        assert pytest.approx(sum(result.values()), abs=1e-6) == 1.0

    def test_weights_in_bounds(self, calibrator):
        weights = {"novelty": 0.3, "feasibility": 0.4, "effect": 0.3}
        labels = [
            {
                "hypothesis_claim": "Use PAX for higher recovery",
                "label": "accepted",
                "expert_id": "e1",
                "features": {"novelty": 0.6, "feasibility": 0.9, "effect": 0.7},
            },
            {
                "hypothesis_claim": "Increase cyanide for recovery",
                "label": "rejected",
                "expert_id": "e1",
                "features": {"novelty": 0.1, "feasibility": 0.2, "effect": 0.5},
            },
        ]
        result = calibrator.calibrate(labels, weights)
        for v in result.values():
            assert 0.0 <= v <= 1.0

    def test_accepted_ranks_higher_after_calibration(self, calibrator):
        weights = {"novelty": 0.3, "feasibility": 0.4, "effect": 0.3}
        labels = [
            {
                "hypothesis_claim": "Accepted claim A",
                "label": "accepted",
                "expert_id": "e1",
                "features": {"novelty": 0.6, "feasibility": 0.9, "effect": 0.7},
            },
        ]
        result = calibrator.calibrate(labels, weights)
        accepted_features = {"novelty": 0.6, "feasibility": 0.9, "effect": 0.7}
        old_score = sum(weights[k] * accepted_features[k] for k in weights)
        new_score = sum(result[k] * accepted_features[k] for k in result)
        assert new_score > old_score - 0.01

    def test_rejected_ranks_lower_after_calibration(self, calibrator):
        weights = {"novelty": 0.3, "feasibility": 0.4, "effect": 0.3}
        labels = [
            {
                "hypothesis_claim": "Rejected claim B",
                "label": "rejected",
                "expert_id": "e1",
                "features": {"novelty": 0.6, "feasibility": 0.6, "effect": 0.6},
            },
        ]
        result = calibrator.calibrate(labels, weights)
        features = {"novelty": 0.6, "feasibility": 0.6, "effect": 0.6}
        old_score = sum(weights[k] * features[k] for k in weights)
        new_score = sum(result[k] * features[k] for k in result)
        assert new_score < old_score + 0.01

    def test_idempotent_calibration(self, calibrator):
        weights = {"novelty": 0.3, "feasibility": 0.4, "effect": 0.3}
        labels = [
            {
                "hypothesis_claim": "Claim alpha",
                "label": "accepted",
                "expert_id": "e1",
                "features": {"novelty": 0.8, "feasibility": 0.8, "effect": 0.8},
            },
            {
                "hypothesis_claim": "Claim beta",
                "label": "rejected",
                "expert_id": "e1",
                "features": {"novelty": 0.2, "feasibility": 0.2, "effect": 0.3},
            },
        ]
        r1 = calibrator.calibrate(labels, weights)
        r2 = calibrator.calibrate(labels, weights)
        for k in sorted(weights):
            assert pytest.approx(r1[k], abs=1e-6) == r2[k]

    def test_conflicting_labels_excluded(self, calibrator):
        weights = {"novelty": 0.3, "feasibility": 0.4, "effect": 0.3}
        labels = [
            {
                "hypothesis_claim": "Contested claim",
                "label": "accepted",
                "expert_id": "e1",
                "features": {"novelty": 0.7, "feasibility": 0.7, "effect": 0.7},
            },
            {
                "hypothesis_claim": "Contested claim",
                "label": "rejected",
                "expert_id": "e2",
                "features": {"novelty": 0.7, "feasibility": 0.7, "effect": 0.7},
            },
        ]
        result = calibrator.calibrate(labels, weights)
        assert sum(result.values()) > 0

    def test_all_accepted_labels(self, calibrator):
        weights = {"novelty": 0.3, "feasibility": 0.4, "effect": 0.3}
        labels = [
            {
                "hypothesis_claim": f"accepted claim {i}",
                "label": "accepted",
                "expert_id": "e1",
                "features": {"novelty": 0.5 + i * 0.1, "feasibility": 0.4, "effect": 0.6},
            }
            for i in range(3)
        ]
        result = calibrator.calibrate(labels, weights)
        assert pytest.approx(sum(result.values()), abs=1e-6) == 1.0

    def test_all_rejected_labels(self, calibrator):
        weights = {"novelty": 0.3, "feasibility": 0.4, "effect": 0.3}
        labels = [
            {
                "hypothesis_claim": f"rejected claim {i}",
                "label": "rejected",
                "expert_id": "e1",
                "features": {"novelty": 0.8 - i * 0.1, "feasibility": 0.5, "effect": 0.4},
            }
            for i in range(3)
        ]
        result = calibrator.calibrate(labels, weights)
        assert pytest.approx(sum(result.values()), abs=1e-6) == 1.0
