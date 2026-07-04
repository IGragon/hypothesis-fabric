from __future__ import annotations

import csv
import os
import tempfile

import pytest

from hfabric.export.csv_writer import write_csv
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


def _sample_result() -> RunResult:
    kpi = KPIParsed(
        goal="increase Au flotation recovery by 5% without raising cyanide use",
        kpi=KPI(metric="Au recovery", direction="increase", target="5%"),
        constraints=["no cyanide increase"],
        language="en",
    )
    chunk = EvidenceChunk(
        chunk_id="chunk_001", doc_id="doc_1",
        text="Xanthate collectors improve gold flotation recovery.",
        meta={"source": "kb", "url": "https://example.com/xanthate", "title": "Xanthate study"},
    )
    return RunResult(
        run_id="run-1", session_id="sess-1",
        query="How can we increase Au flotation recovery?",
        kpi=kpi,
        ranked=[
            ExplainedHypothesis(
                scored=ScoredHypothesis(
                    hypothesis=Hypothesis(
                        claim="Xanthate collector addition increases Au recovery",
                        mechanism="Xanthates chemisorb on gold surfaces",
                        expected_effect="+5-10% Au recovery",
                        evidence_refs=["chunk_001"],
                    ),
                    score=0.85,
                    features={"novelty": 0.5, "feasibility": 0.8, "effect": 0.9, "risk": 0.2, "realizability": 0.7},
                    cited_refs={"chunk_001": chunk},
                ),
                justification="Strong supporting evidence.",
                uncertainty="Lab-scale only.",
                verification_plan="Run pilot test at 50g/t.",
                best_practices="Use sulphidization first.",
                actionable_now="Add 30g/t xanthate.",
                external_urls=["https://example.com/xanthate"],
                graph_neighbourhood=["gold --has_property--> Au recovery"],
            )
        ],
        export_path=None, status="complete",
    )


class TestCsvExport:
    def test_writes_csv_with_correct_path(self, temp_workdir):
        path = write_csv(_sample_result(), "sess-1")
        assert path.endswith("hypotheses.csv")
        assert os.path.isfile(path)

    def test_csv_header_and_rows(self, temp_workdir):
        path = write_csv(_sample_result(), "sess-1")
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames is not None
            assert "rank" in reader.fieldnames
            assert "claim" in reader.fieldnames
            assert "score" in reader.fieldnames
            assert "cited_refs" in reader.fieldnames
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["claim"] == "Xanthate collector addition increases Au recovery"
        assert rows[0]["rank"] == "1"
        assert rows[0]["score"] == "0.8500"
        assert "https://example.com/xanthate" in rows[0]["cited_refs"]

    def test_csv_empty_ranked(self, temp_workdir):
        result = _sample_result().model_copy(deep=True)
        result.ranked = []
        path = write_csv(result, "sess-1")
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert list(reader) == []

    def test_csv_handles_commas_in_fields(self, temp_workdir):
        result = _sample_result().model_copy(deep=True)
        result.ranked[0].scored.hypothesis.claim = "Use 50g/t xanthate, 100g/t Na2S, heat to 60C"
        path = write_csv(result, "sess-1")
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert "50g/t xanthate" in rows[0]["claim"]
        assert rows[0]["claim"].count(",") == 2