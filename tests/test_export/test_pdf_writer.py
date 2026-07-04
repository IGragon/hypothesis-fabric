from __future__ import annotations

import os
import tempfile

import pytest

from hfabric.export.pdf_writer import write_pdf
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
                justification="Strong evidence [chunk_001].",
                uncertainty="Lab-scale only.",
                verification_plan="Run pilot test at 50g/t.",
                graph_neighbourhood=["gold --has_property--> Au recovery"],
            )
        ],
        export_path=None, status="complete",
    )


class TestPdfExport:
    def test_writes_valid_pdf(self, temp_workdir):
        path = write_pdf(_sample_result(), "sess-1")
        assert path.endswith("report.pdf")
        assert os.path.isfile(path)
        with open(path, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_pdf_non_empty(self, temp_workdir):
        path = write_pdf(_sample_result(), "sess-1")
        assert os.path.getsize(path) > 1000

    def test_pdf_empty_ranked_list(self, temp_workdir):
        result = _sample_result().model_copy(deep=True)
        result.ranked = []
        path = write_pdf(result, "sess-1")
        assert os.path.isfile(path)

    def test_pdf_special_characters(self, temp_workdir):
        result = _sample_result().model_copy(deep=True)
        result.ranked[0].scored.hypothesis.claim = "Use 50g/t Xanthate & Na2S at 60°C"
        result.ranked[0].justification = "Evidence supports <10% gain> [chunk_001]"
        path = write_pdf(result, "sess-1")
        assert os.path.isfile(path)