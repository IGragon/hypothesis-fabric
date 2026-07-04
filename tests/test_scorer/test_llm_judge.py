from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hfabric.scorer.llm_judge import JudgeScores, LLMJudge
from hfabric.schemas import Hypothesis


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    response = MagicMock()
    response.content = '{"novelty": 0.7, "feasibility": 0.8, "effect": 0.6, "risk": 0.3}'
    llm.invoke.return_value = response
    return llm


@pytest.fixture
def sample_hyp():
    return Hypothesis(
        claim="Use PAX collector to increase Au recovery",
        mechanism="PAX chemisorbs on gold surfaces",
        expected_effect="+5% Au recovery",
        evidence_refs=["c1"],
    )


class TestLLMJudge:
    def test_judge_returns_scores(self, mock_llm, sample_hyp):
        judge = LLMJudge(mock_llm)
        scores = judge.judge(sample_hyp, [], MagicMock())
        assert scores is not None
        assert scores.novelty == 0.7
        assert scores.feasibility == 0.8
        assert scores.effect == 0.6
        assert scores.risk == 0.3

    def test_judge_returns_none_on_failure(self, sample_hyp):
        llm = MagicMock()
        llm.invoke.side_effect = Exception("LLM error")
        judge = LLMJudge(llm)
        scores = judge.judge(sample_hyp, [], MagicMock())
        assert scores is None

    def test_judge_invalid_json_returns_none(self, sample_hyp):
        llm = MagicMock()
        response = MagicMock()
        response.content = "not valid json"
        llm.invoke.return_value = response
        judge = LLMJudge(llm)
        scores = judge.judge(sample_hyp, [], MagicMock())
        assert scores is None

    def test_judge_clips_scores_to_bounds(self, sample_hyp):
        llm = MagicMock()
        response = MagicMock()
        response.content = '{"novelty": 2.5, "feasibility": -0.5, "effect": 1.5, "risk": -1.0}'
        llm.invoke.return_value = response
        judge = LLMJudge(llm)
        scores = judge.judge(sample_hyp, [], MagicMock())
        assert scores is not None
        assert 0.0 <= scores.novelty <= 1.0
        assert 0.0 <= scores.feasibility <= 1.0
        assert 0.0 <= scores.effect <= 1.0
        assert 0.0 <= scores.risk <= 1.0

    def test_to_dict(self, mock_llm, sample_hyp):
        judge = LLMJudge(mock_llm)
        scores = judge.judge(sample_hyp, [], MagicMock())
        assert scores is not None
        d = scores.to_dict()
        assert set(d.keys()) == {"novelty", "feasibility", "effect", "risk"}

    def test_judge_with_list_content(self, sample_hyp):
        llm = MagicMock()
        response = MagicMock()
        response.content = [{"text": '{"novelty": 0.5, "feasibility": 0.5, "effect": 0.5, "risk": 0.5}'}]
        llm.invoke.return_value = response
        judge = LLMJudge(llm)
        scores = judge.judge(sample_hyp, [], MagicMock())
        assert scores is not None
        assert scores.novelty == 0.5
