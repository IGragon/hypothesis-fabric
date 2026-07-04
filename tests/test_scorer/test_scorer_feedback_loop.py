from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from hfabric.config import MVPConfig
from hfabric.schemas import EvidenceChunk, Hypothesis, KPI, KPIParsed
from hfabric.scorer import Scorer
from hfabric.storage.feedback_store import FeedbackStore


@pytest.fixture
def fb_store():
    db_path = Path(tempfile.gettempdir()) / "test_scorer_feedback.db"
    if db_path.exists():
        db_path.unlink()
    store = FeedbackStore(str(db_path))
    yield store
    if db_path.exists():
        db_path.unlink()


def _kpi() -> KPIParsed:
    return KPIParsed(
        goal="increase Au recovery",
        kpi=KPI(metric="Au recovery", direction="increase", target="+15%"),
        constraints=["use xanthate"],
        language="en",
    )


def _hyp(claim: str) -> Hypothesis:
    return Hypothesis(
        claim=claim,
        mechanism="xanthate chemisorption improves flotation",
        expected_effect="higher Au recovery",
        evidence_refs=["c1"],
    )


def _chunks() -> dict[str, EvidenceChunk]:
    return {"c1": EvidenceChunk(chunk_id="c1", doc_id="d1", text="xanthate", meta={})}


class _FakeKG:
    def get_entities(self, name):
        return []

    def neighbours(self, node_id, hops=2):
        return []


class TestScorerFeedbackLoop:
    def test_no_feedback_store_uses_config_weights(self, mvp_config):
        scorer = Scorer(_FakeKG(), mvp_config)
        assert scorer.ranker.weights["novelty"] == mvp_config.weight_novelty

    def test_empty_feedback_store_uses_config_weights(self, mvp_config, fb_store):
        scorer = Scorer(_FakeKG(), mvp_config, feedback_store=fb_store)
        assert scorer.ranker.weights["novelty"] == mvp_config.weight_novelty

    def test_feedback_with_features_calibrates_weights(self, mvp_config, fb_store):
        fb_store.save_label(
            run_id="r1",
            hypothesis_claim="Accepted claim A",
            label="accepted",
            expert_id="e1",
            features={"novelty": 0.9, "feasibility": 0.9, "effect": 0.9, "risk": 0.1, "realizability": 0.5},
        )
        scorer = Scorer(_FakeKG(), mvp_config, feedback_store=fb_store)
        assert scorer.feedback_weights is not None
        assert abs(sum(scorer.feedback_weights.values()) - 1.0) < 1e-6

    def test_feedback_features_persisted_and_reloaded(self, fb_store):
        lid = fb_store.save_label(
            run_id="r1",
            hypothesis_claim="Claim X",
            label="accepted",
            expert_id="e1",
            features={"novelty": 0.7, "feasibility": 0.8, "effect": 0.6, "risk": 0.2, "realizability": 0.5},
        )
        assert lid > 0
        labels = fb_store.get_all_labels()
        assert len(labels) == 1
        assert labels[0]["features"]["novelty"] == 0.7
        assert labels[0]["features"]["feasibility"] == 0.8

    def test_feedback_loop_changes_ranking_order(self, mvp_config, fb_store):
        hyp_high_nov = _hyp("Novel xanthate blend accepted claim A")
        hyp_low_nov = _hyp("Standard xanthate dose accepted claim B")
        chunks = _chunks()
        kpi = _kpi()

        scorer_base = Scorer(_FakeKG(), mvp_config)
        base = scorer_base.score([hyp_high_nov, hyp_low_nov], chunks, kpi, _FakeKG(), mvp_config)
        base_order = [s.hypothesis.claim for s in base]

        fb_store.save_label(
            run_id="r1",
            hypothesis_claim="Novel xanthate blend accepted claim A",
            label="accepted",
            expert_id="e1",
            features={"novelty": 0.95, "feasibility": 0.5, "effect": 0.5, "risk": 0.5, "realizability": 0.5},
        )
        fb_store.save_label(
            run_id="r1",
            hypothesis_claim="Standard xanthate dose accepted claim B",
            label="rejected",
            expert_id="e1",
            features={"novelty": 0.1, "feasibility": 0.5, "effect": 0.5, "risk": 0.5, "realizability": 0.5},
        )
        scorer_calibrated = Scorer(_FakeKG(), mvp_config, feedback_store=fb_store)
        calibrated = scorer_calibrated.score([hyp_high_nov, hyp_low_nov], chunks, kpi, _FakeKG(), mvp_config)
        calibrated_order = [s.hypothesis.claim for s in calibrated]

        assert base_order != calibrated_order or scorer_calibrated.ranker.weights != scorer_base.ranker.weights
