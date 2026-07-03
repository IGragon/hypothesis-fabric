from __future__ import annotations

import json
import os
import re
import tempfile

import pytest

from hfabric.export.writer import write_export
from hfabric.schemas import (
    EvidenceChunk,
    ExplainedHypothesis,
    Hypothesis,
    KPI,
    KPIParsed,
    RunResult,
    ScoredHypothesis,
)


@pytest.fixture
def temp_workdir(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.chdir(tmpdir)
        yield tmpdir


@pytest.fixture
def sample_run_result():
    kpi = KPIParsed(
        goal="increase Au flotation recovery by 5% without raising cyanide use",
        kpi=KPI(metric="Au recovery", direction="increase", target="5%"),
        constraints=["no cyanide increase"],
        language="en",
    )

    evidence = {
        "chunk_001": EvidenceChunk(
            chunk_id="chunk_001",
            doc_id="doc_1",
            text="Xanthate collectors improve gold flotation recovery.",
            meta={"source": "kb"},
        ),
        "chunk_002": EvidenceChunk(
            chunk_id="chunk_002",
            doc_id="doc_2",
            text="Sodium sulphide activates oxidized gold ores.",
            meta={"source": "session"},
        ),
    }

    ranked = [
        ExplainedHypothesis(
            scored=ScoredHypothesis(
                hypothesis=Hypothesis(
                    claim="Xanthate collector addition increases Au recovery",
                    mechanism="Xanthates chemisorb on gold surfaces increasing hydrophobicity",
                    expected_effect="+5-10% Au recovery",
                    evidence_refs=["chunk_001"],
                ),
                score=0.85,
                features={"novelty": 0.5, "feasibility": 0.8, "effect": 0.9},
                cited_refs={"chunk_001": evidence["chunk_001"]},
            ),
            justification="Strong supporting evidence from literature.",
            uncertainty="Limited to lab-scale results.",
            verification_plan="Run pilot flotation test with 50g/t xanthate.",
            graph_neighbourhood=["gold --has_property--> Au recovery", "xanthate --improves--> gold"],
        ),
        ExplainedHypothesis(
            scored=ScoredHypothesis(
                hypothesis=Hypothesis(
                    claim="Sodium sulphide pre-treatment activates oxidized gold",
                    mechanism="Sulphidization forms a hydrophobic layer on oxidized gold particles",
                    expected_effect="+3-7% Au recovery for oxidized ores",
                    evidence_refs=["chunk_002"],
                ),
                score=0.72,
                features={"novelty": 0.6, "feasibility": 0.7, "effect": 0.7},
                cited_refs={"chunk_002": evidence["chunk_002"]},
            ),
            justification="Relevant for oxidized ores in current circuit.",
            uncertainty="Sulphidization dosage needs optimization.",
            verification_plan="Test Na2S at 100-500g/t on oxide samples.",
            graph_neighbourhood=["sodium_sulphide --activates--> oxidized_gold"],
        ),
    ]

    return RunResult(
        run_id="test-run-001",
        session_id="test-session",
        query="How can we increase Au flotation recovery?",
        kpi=kpi,
        ranked=ranked,
        export_path=None,
        status="complete",
    )


class TestWriteExport:
    def test_json_file_valid_and_contains_all_data(self, temp_workdir, sample_run_result):
        json_path, md_path = write_export(sample_run_result, sample_run_result.session_id)

        assert os.path.exists(json_path)
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["run_id"] == "test-run-001"
        assert data["query"] == "How can we increase Au flotation recovery?"
        assert data["status"] == "complete"
        assert data["kpi"]["kpi"]["metric"] == "Au recovery"
        assert len(data["ranked"]) == 2
        assert data["ranked"][0]["scored"]["hypothesis"]["claim"] == "Xanthate collector addition increases Au recovery"
        assert data["ranked"][0]["scored"]["score"] == 0.85

    def test_markdown_contains_key_sections(self, temp_workdir, sample_run_result):
        json_path, md_path = write_export(sample_run_result, sample_run_result.session_id)

        assert os.path.exists(md_path)
        with open(md_path, encoding="utf-8") as f:
            content = f.read()

        assert "Hypothesis Fabric" in content
        assert "Research Report" in content
        assert sample_run_result.query in content
        assert sample_run_result.run_id in content
        assert "KPI Summary" in content
        assert "Au recovery" in content
        assert "Ranked Hypotheses" in content
        assert "#1." in content
        assert "Xanthate collector addition increases Au recovery" in content
        assert "Score: 0.85" in content
        assert "Mechanism:" in content
        assert "Expected Effect:" in content
        assert "Justification:" in content
        assert "Uncertainty:" in content
        assert "Verification Plan:" in content
        assert "Knowledge Graph Neighbourhood" in content
        assert "gold --has_property--> Au recovery" in content
        assert "---" in content

    def test_idempotent(self, temp_workdir, sample_run_result):
        json_path_1, md_path_1 = write_export(sample_run_result, sample_run_result.session_id)

        with open(json_path_1, encoding="utf-8") as f:
            json_content_1 = f.read()
        with open(md_path_1, encoding="utf-8") as f:
            md_content_1 = f.read()

        json_path_2, md_path_2 = write_export(sample_run_result, sample_run_result.session_id)

        with open(json_path_2, encoding="utf-8") as f:
            json_content_2 = f.read()
        with open(md_path_2, encoding="utf-8") as f:
            md_content_2 = f.read()

        assert json_path_1 == json_path_2
        assert md_path_1 == md_path_2
        assert json_content_1 == json_content_2
        assert md_content_1 == md_content_2

    def test_empty_ranked_list(self, temp_workdir, sample_run_result):
        result = sample_run_result.model_copy(deep=True)
        result.ranked = []

        json_path, md_path = write_export(result, result.session_id)

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["ranked"] == []

        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        assert "Ranked Hypotheses" in content
        assert "#1." not in content

    def test_special_characters(self, temp_workdir, sample_run_result):
        result = sample_run_result.model_copy(deep=True)
        result.query = "How to *improve* <Au> & \"flotation\" recovery?"
        result.ranked[0].scored.hypothesis.claim = "Use **Xanthate** (<100g/t) & Na2S"
        result.ranked[0].scored.hypothesis.mechanism = "Chemisorption on [gold] surfaces"
        result.ranked[0].scored.cited_refs["chunk_001"].text = "Xanthate > 50g/t is *effective*"

        json_path, md_path = write_export(result, result.session_id)

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "How to" in data["query"]
        assert "*" in data["query"]

        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        assert "How to *improve* <Au>" in content
        assert "Use **Xanthate**" in content
        assert "Chemisorption on [gold] surfaces" in content
        assert "> Xanthate > 50g/t is *effective*" in content

    def test_paths_created_correctly(self, temp_workdir, sample_run_result):
        json_path, md_path = write_export(sample_run_result, "session-abc")

        expected_dir = os.path.join("sessions", "session-abc", "export")
        assert os.path.isdir(expected_dir)
        assert json_path == os.path.join(expected_dir, "hypotheses.json")
        assert md_path == os.path.join(expected_dir, "report.md")

    def test_no_constraints(self, temp_workdir, sample_run_result):
        result = sample_run_result.model_copy(deep=True)
        result.kpi.constraints = []

        json_path, md_path = write_export(result, result.session_id)

        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        assert "Constraints:** None" in content

    def test_kpi_target_none(self, temp_workdir, sample_run_result):
        result = sample_run_result.model_copy(deep=True)
        result.kpi.kpi.target = None

        json_path, md_path = write_export(result, result.session_id)

        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        assert "N/A" in content

    def test_no_evidence_no_neighbourhood(self, temp_workdir, sample_run_result):
        result = sample_run_result.model_copy(deep=True)
        result.ranked[0].scored.cited_refs = {}
        result.ranked[0].graph_neighbourhood = []

        json_path, md_path = write_export(result, result.session_id)

        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        assert "Evidence:** None" in content
        assert "Knowledge Graph Neighbourhood:** None" in content


def test_write_export_returns_correct_types(temp_workdir, sample_run_result):
    json_path, md_path = write_export(sample_run_result, sample_run_result.session_id)
    assert isinstance(json_path, str)
    assert isinstance(md_path, str)
    assert json_path.endswith("hypotheses.json")
    assert md_path.endswith("report.md")


def test_export_path_set_in_result(temp_workdir, sample_run_result):
    result = sample_run_result.model_copy(deep=True)
    result.export_path = None
    json_path, md_path = write_export(result, result.session_id)
    assert json_path is not None
    assert md_path is not None
