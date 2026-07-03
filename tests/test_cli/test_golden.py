from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from hfabric.schemas import EvidenceChunk, Hypothesis, KPIParsed, KPI, ScoredHypothesis, ExplainedHypothesis
from tests.golden import load_golden_hypotheses, match_golden


class TestLoadGoldenHypotheses:
    def test_loads_from_default_path(self):
        golden = load_golden_hypotheses()
        assert len(golden) == 2
        assert "claim" in golden[0]
        assert "keywords" in golden[0]

    def test_loads_from_custom_path(self, tmp_path):
        custom = [{"claim": "custom", "mechanism": "m", "expected_effect": "e", "evidence_refs": [], "keywords": []}]
        p = tmp_path / "golden.json"
        p.write_text(json.dumps(custom))
        result = load_golden_hypotheses(str(p))
        assert result == custom


class TestMatchGolden:
    def test_exact_match_passes(self):
        golden = [{
            "claim": "Xanthate collector addition increases Au flotation recovery",
            "keywords": ["xanthate", "collector", "gold", "recovery", "flotation"],
        }]
        candidates = [
            Hypothesis(
                claim="Xanthate collector addition increases Au flotation recovery",
                mechanism="Xanthates chemisorb on gold surfaces",
                expected_effect="+5-10% Au recovery",
                evidence_refs=["c1"],
            ),
        ]
        result = match_golden(candidates, golden)
        assert result["passed"] is True
        assert result["matched_count"] == 1

    def test_partial_match_passes(self):
        golden = [{
            "claim": "Xanthate collector addition increases Au flotation recovery",
            "keywords": ["xanthate", "collector", "gold", "recovery", "flotation"],
        }]
        candidates = [
            Hypothesis(
                claim="Adding xanthate collector improves gold flotation recovery rate",
                mechanism="Collector increases hydrophobicity of gold particles",
                expected_effect="Significant increase in Au recovery",
                evidence_refs=["c1"],
            ),
        ]
        result = match_golden(candidates, golden)
        assert result["passed"] is True

    def test_no_match_fails(self):
        golden = [{
            "claim": "Xanthate collector addition increases Au flotation recovery",
            "keywords": ["xanthate", "collector", "gold", "recovery", "flotation"],
        }]
        candidates = [
            Hypothesis(
                claim="Completely unrelated hypothesis about weather patterns",
                mechanism="Atmospheric pressure changes cause rain",
                expected_effect="More rain",
                evidence_refs=["c1"],
            ),
        ]
        result = match_golden(candidates, golden)
        assert result["passed"] is False
        assert result["matched_count"] == 0

    def test_multiple_golden_multiple_matches(self):
        golden = load_golden_hypotheses()
        candidates = [
            Hypothesis(
                claim="Xanthate collector addition increases Au flotation recovery",
                mechanism="Xanthates chemisorb on gold surfaces",
                expected_effect="+5-10% Au recovery",
                evidence_refs=["c1"],
            ),
            Hypothesis(
                claim="Sodium sulphide pre-treatment activates oxidized gold ores for flotation",
                mechanism="Sulphidization forms hydrophobic layer",
                expected_effect="+3-7% Au recovery for oxidized ores",
                evidence_refs=["c2"],
            ),
        ]
        result = match_golden(candidates, golden)
        assert result["passed"] is True
        assert result["matched_count"] == 2


class TestGoldenIntegrationWithOrchestrator:
    def test_orchestrator_output_matches_golden(self):
        from tests.test_orchestrator.fakes import (
            FakeCitation, FakeExplainer, FakeGenerator, FakeKG,
            FakeRetriever, FakeScorer, FakeTraceCollector,
            make_fake_llm, make_valid_hypotheses,
        )
        from hfabric.config import MVPConfig
        from hfabric.orchestrator.wiring import build_real_orchestrator
        from hfabric.storage.session_store import SessionStore

        config = MVPConfig()
        llm = make_fake_llm()
        kg = FakeKG()
        store = SessionStore(":memory:")

        orch = build_real_orchestrator(
            config,
            llm=llm,
            kg=kg,
            store=store,
            retriever=FakeRetriever(),
            generator=FakeGenerator([make_valid_hypotheses()]),
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            trace_collector=FakeTraceCollector(),
        )

        state = orch.run("golden_test", "increase Au flotation recovery")

        explained = state.get("explained", [])
        candidates: list[Hypothesis] = []
        for e in explained:
            hyp_dict = e.get("scored", {}).get("hypothesis", {})
            candidates.append(Hypothesis(**hyp_dict))

        result = match_golden(candidates)
        assert result["passed"] is True
        assert result["matched_count"] >= 1
