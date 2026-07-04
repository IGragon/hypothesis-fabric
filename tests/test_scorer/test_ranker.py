from __future__ import annotations

import pytest

from hfabric.scorer.ranker import WeightedRanker
from hfabric.schemas import Hypothesis, ScoredHypothesis


class TestWeightedRanker:
    def test_ranks_by_score_descending(self):
        ranker = WeightedRanker()
        hypotheses = [
            {
                "hypothesis": Hypothesis(
                    claim="claim_a",
                    mechanism="m",
                    expected_effect="e",
                    evidence_refs=[],
                ),
                "features": {"novelty": 0.3, "feasibility": 0.3, "effect": 0.3},
            },
            {
                "hypothesis": Hypothesis(
                    claim="claim_b",
                    mechanism="m",
                    expected_effect="e",
                    evidence_refs=[],
                ),
                "features": {"novelty": 0.9, "feasibility": 0.9, "effect": 0.9},
            },
        ]
        result = ranker.rank(hypotheses)
        assert result[0].score >= result[1].score
        assert result[0].hypothesis.claim == "claim_b"
        assert result[1].hypothesis.claim == "claim_a"

    def test_tie_break_by_hash_deterministic(self):
        ranker = WeightedRanker()
        hypotheses = [
            {
                "hypothesis": Hypothesis(
                    claim="tie_claim_a",
                    mechanism="m",
                    expected_effect="e",
                    evidence_refs=[],
                ),
                "features": {"novelty": 0.5, "feasibility": 0.5, "effect": 0.5},
            },
            {
                "hypothesis": Hypothesis(
                    claim="tie_claim_b",
                    mechanism="m",
                    expected_effect="e",
                    evidence_refs=[],
                ),
                "features": {"novelty": 0.5, "feasibility": 0.5, "effect": 0.5},
            },
        ]
        r1 = ranker.rank(hypotheses)
        r2 = ranker.rank(hypotheses)
        assert [s.hypothesis.claim for s in r1] == [s.hypothesis.claim for s in r2]

    def test_weighted_score_calculation(self):
        ranker = WeightedRanker(weights={"novelty": 0.5, "feasibility": 0.3, "effect": 0.2})
        hypotheses = [
            {
                "hypothesis": Hypothesis(
                    claim="c",
                    mechanism="m",
                    expected_effect="e",
                    evidence_refs=[],
                ),
                "features": {"novelty": 1.0, "feasibility": 0.0, "effect": 0.0},
            },
        ]
        result = ranker.rank(hypotheses)
        assert result[0].score == pytest.approx(0.5)

    def test_uses_default_weights_when_none_given(self):
        ranker = WeightedRanker()
        assert ranker.weights["novelty"] == 0.20
        assert ranker.weights["feasibility"] == 0.25
        assert ranker.weights["effect"] == 0.20
        assert ranker.weights["risk"] == 0.10
        assert ranker.weights["realizability"] == 0.10
        assert ranker.weights["evidence"] == 0.10
        assert ranker.weights["violation"] == 0.15

    def test_cited_refs_is_empty(self):
        ranker = WeightedRanker()
        hypotheses = [
            {
                "hypothesis": Hypothesis(
                    claim="c",
                    mechanism="m",
                    expected_effect="e",
                    evidence_refs=["chunk_001"],
                ),
                "features": {"novelty": 0.5, "feasibility": 0.5, "effect": 0.5},
            },
        ]
        result = ranker.rank(hypotheses)
        assert result[0].cited_refs == {}

    def test_features_preserved_in_output(self):
        ranker = WeightedRanker()
        features = {"novelty": 0.1, "feasibility": 0.2, "effect": 0.3}
        hypotheses = [
            {
                "hypothesis": Hypothesis(
                    claim="c",
                    mechanism="m",
                    expected_effect="e",
                    evidence_refs=[],
                ),
                "features": features,
            },
        ]
        result = ranker.rank(hypotheses)
        assert result[0].features == features

    def test_deterministic_sort_order(self):
        ranker = WeightedRanker()
        hypotheses = [
            {
                "hypothesis": Hypothesis(
                    claim=f"claim_{i}",
                    mechanism="m",
                    expected_effect="e",
                    evidence_refs=[],
                ),
                "features": {"novelty": 0.5, "feasibility": 0.5, "effect": 0.5},
            }
            for i in range(5)
        ]
        r1 = ranker.rank(hypotheses)
        r2 = ranker.rank(hypotheses)
        assert r1 == r2
