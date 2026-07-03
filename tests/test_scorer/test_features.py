from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hfabric.scorer.features import extract_effect, extract_feasibility, extract_novelty
from hfabric.schemas import Hypothesis, KPI, KPIParsed, KGNode


class TestExtractNovelty:
    def test_returns_neutral_for_empty_hypothesis(self, fake_kg):
        hyp = Hypothesis(
            claim="test",
            mechanism="test",
            expected_effect="test",
            evidence_refs=[],
        )
        result = extract_novelty(hyp, fake_kg)
        assert result == 0.5

    def test_returns_neutral_when_kg_is_none(self):
        hyp = Hypothesis(
            claim="Xanthate collector addition increases Au recovery",
            mechanism="Xanthates chemisorb on gold surfaces",
            expected_effect="+5% Au recovery",
            evidence_refs=[],
        )
        result = extract_novelty(hyp, None)
        assert result == 0.5

    def test_returns_neutral_when_entity_not_in_kg(self, fake_kg):
        fake_kg.get_entities.return_value = []
        hyp = Hypothesis(
            claim="Xanthate addition",
            mechanism="test",
            expected_effect="test",
            evidence_refs=[],
        )
        result = extract_novelty(hyp, fake_kg)
        assert result == 0.5

    def test_returns_high_novelty_for_few_neighbours(self, fake_kg):
        fake_kg.get_entities.return_value = [
            KGNode(id="node_1", label="Material", properties={"name": "gold"}),
        ]
        fake_kg.neighbours.return_value = []
        hyp = Hypothesis(
            claim="Xanthate collector addition increases Au recovery",
            mechanism="Xanthates chemisorb on gold surfaces",
            expected_effect="+5% Au recovery",
            evidence_refs=[],
        )
        result = extract_novelty(hyp, fake_kg)
        assert result > 0.8

    def test_returns_low_novelty_for_many_neighbours(self, fake_kg):
        fake_kg.get_entities.return_value = [
            KGNode(id="node_1", label="Material", properties={"name": "gold"}),
        ]
        fake_kg.neighbours.return_value = [KGNode(id=f"n{i}", label="P", properties={}) for i in range(15)]
        hyp = Hypothesis(
            claim="Xanthate collector addition increases Au recovery",
            mechanism="test",
            expected_effect="test",
            evidence_refs=[],
        )
        result = extract_novelty(hyp, fake_kg)
        assert result < 0.3

    def test_handles_kg_errors_gracefully(self, fake_kg):
        fake_kg.get_entities.side_effect = Exception("KG down")
        hyp = Hypothesis(
            claim="Xanthate addition increases Au recovery",
            mechanism="test",
            expected_effect="test",
            evidence_refs=[],
        )
        result = extract_novelty(hyp, fake_kg)
        assert result == 0.5

    def test_deterministic_same_input(self, fake_kg):
        hyp = Hypothesis(
            claim="Xanthate collector addition increases Au recovery",
            mechanism="Xanthates chemisorb on gold surfaces",
            expected_effect="+5% Au recovery",
            evidence_refs=[],
        )
        r1 = extract_novelty(hyp, fake_kg)
        r2 = extract_novelty(hyp, fake_kg)
        assert r1 == r2


class TestExtractFeasibility:
    def test_returns_full_score_when_no_constraints(self):
        hyp = Hypothesis(
            claim="Xanthate addition",
            mechanism="test",
            expected_effect="test",
            evidence_refs=[],
        )
        result = extract_feasibility(hyp, [])
        assert result == 1.0

    def test_returns_full_score_when_all_satisfied(self):
        hyp = Hypothesis(
            claim="Sodium sulphide pre-treatment without cyanide",
            mechanism="Sulphidization improves flotation without raising cyanide",
            expected_effect="improved flotation",
            evidence_refs=[],
        )
        constraints = ["no cyanide increase"]
        result = extract_feasibility(hyp, constraints)
        assert result == 1.0

    def test_returns_zero_when_negation_constraint_violated(self):
        hyp = Hypothesis(
            claim="Increase cyanide to improve recovery",
            mechanism="Higher cyanide concentration increases gold dissolution",
            expected_effect="higher Au recovery",
            evidence_refs=[],
        )
        constraints = ["no cyanide increase"]
        result = extract_feasibility(hyp, constraints)
        assert result == 0.0

    def test_mixed_constraints_partial_score(self):
        hyp = Hypothesis(
            claim="Use xanthate to improve Au recovery",
            mechanism="Xanthate chemisorption improves flotation",
            expected_effect="improved Au recovery",
            evidence_refs=[],
        )
        constraints = ["increase Au recovery", "no cyanide increase"]
        result = extract_feasibility(hyp, constraints)
        assert result == 1.0

    def test_deterministic_same_input(self):
        hyp = Hypothesis(
            claim="test claim",
            mechanism="test mechanism",
            expected_effect="test effect",
            evidence_refs=[],
        )
        constraints = ["no cyanide increase", "increase Au recovery"]
        r1 = extract_feasibility(hyp, constraints)
        r2 = extract_feasibility(hyp, constraints)
        assert r1 == r2


class TestExtractEffect:
    def test_returns_high_score_for_matching_metric(self, sample_kpi):
        hyp = Hypothesis(
            claim="Xanthate addition",
            mechanism="test",
            expected_effect="Au recovery increase by 5%",
            evidence_refs=[],
        )
        result = extract_effect(hyp, sample_kpi)
        assert result > 0.5

    def test_returns_low_score_for_unrelated_effect(self, sample_kpi):
        hyp = Hypothesis(
            claim="something else",
            mechanism="different",
            expected_effect="reduces water consumption",
            evidence_refs=[],
        )
        result = extract_effect(hyp, sample_kpi)
        assert result <= 0.5

    def test_direction_boost_for_increase(self, sample_kpi):
        hyp_with = Hypothesis(
            claim="test",
            mechanism="test",
            expected_effect="increase Au recovery by 5%",
            evidence_refs=[],
        )
        hyp_without = Hypothesis(
            claim="test",
            mechanism="test",
            expected_effect="Au recovery 5%",
            evidence_refs=[],
        )
        score_with = extract_effect(hyp_with, sample_kpi)
        score_without = extract_effect(hyp_without, sample_kpi)
        assert score_with >= score_without

    def test_handles_empty_kpi_tokens(self):
        kpi = KPIParsed(
            goal="",
            kpi=KPI(metric="", direction="increase", target=""),
            constraints=[],
            language="en",
        )
        hyp = Hypothesis(
            claim="test",
            mechanism="test",
            expected_effect="test",
            evidence_refs=[],
        )
        result = extract_effect(hyp, kpi)
        assert result == 0.5

    def test_deterministic_same_input(self, sample_kpi):
        hyp = Hypothesis(
            claim="test",
            mechanism="test",
            expected_effect="increase Au recovery by 5%",
            evidence_refs=[],
        )
        r1 = extract_effect(hyp, sample_kpi)
        r2 = extract_effect(hyp, sample_kpi)
        assert r1 == r2
