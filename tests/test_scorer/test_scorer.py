from __future__ import annotations

from hfabric.scorer import Scorer
from hfabric.schemas import ScoredHypothesis


class TestScorer:
    def test_score_returns_list_of_scored_hypothesis(self, mvp_config, fake_kg, sample_hypotheses, sample_chunks, sample_kpi):
        scorer = Scorer(fake_kg, mvp_config)
        chunks_dict = {c.chunk_id: c for c in sample_chunks}
        result = scorer.score(sample_hypotheses, chunks_dict, sample_kpi, fake_kg, mvp_config)
        assert isinstance(result, list)
        assert len(result) == len(sample_hypotheses)
        for item in result:
            assert isinstance(item, ScoredHypothesis)
            assert 0.0 <= item.score <= 1.0
            assert "novelty" in item.features
            assert "feasibility" in item.features
            assert "effect" in item.features
            assert "risk" in item.features
            assert "realizability" in item.features

    def test_score_returns_sorted_by_score(self, mvp_config, fake_kg, sample_hypotheses, sample_chunks, sample_kpi):
        scorer = Scorer(fake_kg, mvp_config)
        chunks_dict = {c.chunk_id: c for c in sample_chunks}
        result = scorer.score(sample_hypotheses, chunks_dict, sample_kpi, fake_kg, mvp_config)
        scores = [s.score for s in result]
        assert scores == sorted(scores, reverse=True)

    def test_score_is_deterministic(self, mvp_config, fake_kg, sample_hypotheses, sample_chunks, sample_kpi):
        scorer = Scorer(fake_kg, mvp_config)
        chunks_dict = {c.chunk_id: c for c in sample_chunks}
        r1 = scorer.score(sample_hypotheses, chunks_dict, sample_kpi, fake_kg, mvp_config)
        r2 = scorer.score(sample_hypotheses, chunks_dict, sample_kpi, fake_kg, mvp_config)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.hypothesis.claim == b.hypothesis.claim
            assert a.score == b.score
            assert a.features == b.features

    def test_uses_config_weights(self, mvp_config, fake_kg, sample_hypotheses, sample_chunks, sample_kpi):
        scorer = Scorer(fake_kg, mvp_config)
        assert scorer.ranker.weights["novelty"] == mvp_config.weight_novelty
        assert scorer.ranker.weights["feasibility"] == mvp_config.weight_feasibility
        assert scorer.ranker.weights["effect"] == mvp_config.weight_effect
        assert scorer.ranker.weights["risk"] == mvp_config.weight_risk
        assert scorer.ranker.weights["realizability"] == mvp_config.weight_realizability
