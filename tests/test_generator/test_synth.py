from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

import pytest

from hfabric.config import MVPConfig
from hfabric.generator.synth import (
    CandidateSynthesizer,
    HypothesisList,
    _build_prompt,
    _validate_hypothesis,
)
from hfabric.schemas import Hypothesis, TraceRecord


MIN_VALID = "sufficiently long text here"
_SENTINEL = object()


def _hypothesis(claim=MIN_VALID, mechanism=MIN_VALID, expected_effect=MIN_VALID, evidence_refs=_SENTINEL):
    refs = ["chunk_001"] if evidence_refs is _SENTINEL else evidence_refs
    return Hypothesis(
        claim=claim,
        mechanism=mechanism,
        expected_effect=expected_effect,
        evidence_refs=refs,
    )


class _FakeStructured:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def invoke(self, messages):
        if self.call_count >= len(self.responses):
            return self.responses[-1]
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp


class _FakeLLM(MagicMock):
    def __init__(self, structured_responses=None):
        super().__init__()
        self._structured = _FakeStructured(structured_responses or [])
        self._with_structured_calls: list[tuple] = []

    def with_structured_output(self, schema, method="json_schema"):
        self._with_structured_calls.append((schema, method))
        return self._structured


class TestValidateHypothesis:
    def test_valid_hypothesis_passes(self):
        h = _hypothesis(evidence_refs=["chunk_001"])
        errors = _validate_hypothesis(h, {"chunk_001", "chunk_002"})
        assert errors == []

    def test_empty_evidence_refs_rejected(self):
        h = _hypothesis(evidence_refs=[])
        errors = _validate_hypothesis(h, {"chunk_001"})
        assert len(errors) >= 1
        assert any("empty evidence_refs" in e for e in errors)

    def test_unknown_chunk_id_flagged(self):
        h = _hypothesis(evidence_refs=["chunk_999"])
        errors = _validate_hypothesis(h, {"chunk_001", "chunk_002"})
        assert len(errors) >= 1
        assert any("unknown chunk_id" in e for e in errors)

    def test_short_claim_rejected(self):
        h = _hypothesis(claim="short", mechanism=MIN_VALID, expected_effect=MIN_VALID)
        errors = _validate_hypothesis(h, {"chunk_001"})
        assert any("claim too short" in e for e in errors)

    def test_short_mechanism_rejected(self):
        h = _hypothesis(claim=MIN_VALID, mechanism="short", expected_effect=MIN_VALID)
        errors = _validate_hypothesis(h, {"chunk_001"})
        assert any("mechanism too short" in e for e in errors)

    def test_short_expected_effect_rejected(self):
        h = _hypothesis(claim=MIN_VALID, mechanism=MIN_VALID, expected_effect="short")
        errors = _validate_hypothesis(h, {"chunk_001"})
        assert any("expected_effect too short" in e for e in errors)

    def test_multiple_errors_reported(self):
        h = _hypothesis(claim="x", mechanism="x", expected_effect="x", evidence_refs=["chunk_999"])
        errors = _validate_hypothesis(h, {"chunk_001"})
        assert len(errors) >= 3


class TestBuildPrompt:
    def test_includes_kpi_goal(self, sample_chunks, sample_kpi):
        prompt = _build_prompt(sample_chunks, sample_kpi)
        assert sample_kpi.goal in prompt["user"]

    def test_includes_kpi_metric(self, sample_chunks, sample_kpi):
        prompt = _build_prompt(sample_chunks, sample_kpi)
        assert sample_kpi.kpi.metric in prompt["user"]
        assert sample_kpi.kpi.direction in prompt["user"]

    def test_includes_constraints(self, sample_chunks, sample_kpi):
        prompt = _build_prompt(sample_chunks, sample_kpi)
        assert sample_kpi.constraints[0] in prompt["user"]

    def test_includes_language(self, sample_chunks, sample_kpi):
        prompt = _build_prompt(sample_chunks, sample_kpi)
        assert sample_kpi.language in prompt["user"]

    def test_includes_chunk_ids(self, sample_chunks, sample_kpi):
        prompt = _build_prompt(sample_chunks, sample_kpi)
        for c in sample_chunks:
            assert c.chunk_id in prompt["user"]

    def test_includes_chunk_texts(self, sample_chunks, sample_kpi):
        prompt = _build_prompt(sample_chunks, sample_kpi)
        for c in sample_chunks:
            assert c.text[:20] in prompt["user"]


class TestCandidateSynthesizer:
    def test_valid_generation_returns_hypotheses(self, sample_chunks, sample_kpi):
        valid = [
            _hypothesis(claim="Xanthate increase test", evidence_refs=["chunk_001"]),
            _hypothesis(claim="Sulphide activation test", evidence_refs=["chunk_003"]),
        ]
        llm = _FakeLLM([HypothesisList(hypotheses=valid)])
        synth = CandidateSynthesizer(llm, MVPConfig(fe2_max_reprompt=3))
        result = synth.generate(sample_chunks, sample_kpi)
        assert len(result) == 2
        assert all(isinstance(h, Hypothesis) for h in result)
        assert result[0].claim == "Xanthate increase test"

    def test_empty_evidence_returns_empty(self, sample_kpi):
        config = MVPConfig(fe2_max_reprompt=1)
        synth = CandidateSynthesizer(_FakeLLM([]), config)
        result = synth.generate([], sample_kpi)
        assert result == []

    def test_retry_on_invalid_output(self, sample_chunks, sample_kpi):
        invalid = [
            _hypothesis(claim="Test", evidence_refs=[]),  # empty refs
        ]
        valid = [
            _hypothesis(claim="Fixed claim here", evidence_refs=["chunk_001"]),
        ]
        config = MVPConfig(fe2_max_reprompt=3)
        llm = _FakeLLM([
            HypothesisList(hypotheses=invalid),
            HypothesisList(hypotheses=valid),
        ])
        synth = CandidateSynthesizer(llm, config)
        result = synth.generate(sample_chunks, sample_kpi)
        assert len(result) == 1
        assert result[0].claim == "Fixed claim here"
        assert llm._structured.call_count == 2

    def test_retry_capped_at_max_reprompt(self, sample_chunks, sample_kpi):
        invalid = [
            _hypothesis(claim="Test", evidence_refs=[]),
        ]
        config = MVPConfig(fe2_max_reprompt=2)
        llm = _FakeLLM([HypothesisList(hypotheses=invalid)] * 10)
        synth = CandidateSynthesizer(llm, config)
        result = synth.generate(sample_chunks, sample_kpi)
        assert result == []
        assert llm._structured.call_count == config.fe2_max_reprompt + 1

    def test_llm_exception_retry_then_return_empty(self, sample_chunks, sample_kpi):
        class _FailingStructured:
            call_count = 0

            def invoke(self, messages):
                self.call_count += 1
                raise RuntimeError("LLM error")

        llm = _FakeLLM([])
        failing = _FailingStructured()
        llm._structured = failing

        config = MVPConfig(fe2_max_reprompt=1)
        synth = CandidateSynthesizer(llm, config)
        result = synth.generate(sample_chunks, sample_kpi)
        assert result == []
        assert failing.call_count == config.fe2_max_reprompt + 1

    def test_trace_populated_on_success(self, sample_chunks, sample_kpi):
        valid = [
            _hypothesis(claim="Xanthate increase test", evidence_refs=["chunk_001"]),
        ]
        llm = _FakeLLM([HypothesisList(hypotheses=valid)])
        synth = CandidateSynthesizer(llm, MVPConfig())
        trace = TraceRecord(run_id="r1", stage="gen", slot="T7")
        result = synth.generate(sample_chunks, sample_kpi, trace)
        assert len(result) == 1
        assert trace.status == "ok"
        assert trace.latency_ms >= 0

    def test_trace_status_error_on_failure(self, sample_chunks, sample_kpi):
        invalid = [
            _hypothesis(claim="Test", evidence_refs=[]),
        ]
        config = MVPConfig(fe2_max_reprompt=0)
        llm = _FakeLLM([HypothesisList(hypotheses=invalid)])
        synth = CandidateSynthesizer(llm, config)
        trace = TraceRecord(run_id="r1", stage="gen", slot="T7")
        result = synth.generate(sample_chunks, sample_kpi, trace)
        assert result == []
        assert trace.status == "error"

    def test_with_structured_output_called_with_hypothesis_list(self):
        llm = _FakeLLM([])
        CandidateSynthesizer(llm, MVPConfig())
        assert len(llm._with_structured_calls) == 1
        assert llm._with_structured_calls[0][0] is HypothesisList
