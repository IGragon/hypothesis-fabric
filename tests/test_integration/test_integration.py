from __future__ import annotations

import json
import os
import shutil
import tempfile
from unittest.mock import MagicMock

import pytest

from hfabric.config import MVPConfig
from hfabric.orchestrator.wiring import build_real_orchestrator
from hfabric.obs.evals import jaccard_at_10
from hfabric.schemas import (
    EvidenceChunk,
    ExplainedHypothesis,
    Hypothesis,
    KGNode,
    KPIParsed,
    KPI,
    ScoredHypothesis,
)
from hfabric.storage.session_store import SessionStore

from tests.test_orchestrator.fakes import (
    FakeCitation,
    FakeExplainer,
    FakeExporter,
    FakeGenerator,
    FakeKG,
    FakeRetriever,
    FakeScorer,
    FakeTraceCollector,
    make_fake_llm,
    make_valid_hypotheses,
)


def _make_evidenced_explained() -> list[ExplainedHypothesis]:
    hyp = Hypothesis(
        claim="Xanthate collector addition increases Au recovery significantly",
        mechanism="Xanthates chemisorb on gold surfaces increasing hydrophobicity",
        expected_effect="+5-10% Au recovery in flotation",
        evidence_refs=["c1"],
    )
    chunk = EvidenceChunk(
        chunk_id="c1", doc_id="d1",
        text="Xanthate collectors improve gold flotation recovery by up to 10%.",
        meta={"source": "kb"},
    )
    scored = ScoredHypothesis(
        hypothesis=hyp, score=0.85,
        features={"novelty": 0.5, "feasibility": 0.8, "effect": 0.9},
        cited_refs={"c1": chunk},
    )
    return [
        ExplainedHypothesis(
            scored=scored,
            justification="Plausible based on metallurgical evidence.",
            uncertainty="Industrial scale-up may differ from lab results.",
            verification_plan="Run controlled flotation test with varying xanthate dosage.",
            graph_neighbourhood=["Material: gold", "Property: Au recovery"],
        )
    ]


@pytest.fixture
def config():
    return MVPConfig()


@pytest.fixture
def fake_llm():
    return make_fake_llm()


@pytest.fixture
def fake_kg():
    return FakeKG()


@pytest.fixture
def in_memory_store():
    return SessionStore(":memory:")


class TestBuildRealOrchestrator:
    def test_returns_orchestrator_with_all_overrides(self, config, fake_llm, fake_kg, in_memory_store):
        orch = build_real_orchestrator(
            config,
            llm=fake_llm,
            kg=fake_kg,
            store=in_memory_store,
            retriever=FakeRetriever(),
            generator=FakeGenerator([make_valid_hypotheses()]),
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            trace_collector=FakeTraceCollector(),
        )
        assert orch is not None
        assert orch._graph is not None

    def test_uses_real_adapters_when_not_overridden(self, config, fake_llm, fake_kg, in_memory_store):
        orch = build_real_orchestrator(
            config,
            llm=fake_llm,
            kg=fake_kg,
            store=in_memory_store,
            retriever=FakeRetriever(),
        )
        result = orch.run("test_session", "Increase Au recovery by 5% without raising cyanide use")
        assert result["status"] == "complete"


class TestEndToEndSmoke:
    def test_pipeline_runs_all_stages(self, config, fake_llm, fake_kg, in_memory_store, tmp_path):
        session_id = "test_smoke"
        export_dir = tmp_path / "sessions" / session_id
        export_dir.mkdir(parents=True)

        generator = FakeGenerator([make_valid_hypotheses()])
        tc = FakeTraceCollector()

        orch = build_real_orchestrator(
            config,
            llm=fake_llm,
            kg=fake_kg,
            store=in_memory_store,
            retriever=FakeRetriever(),
            generator=generator,
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            trace_collector=tc,
        )

        result = orch.run(session_id, "Increase Au recovery by 5% without raising cyanide use")

        assert result["status"] == "complete"
        assert result["nl_query"] == "Increase Au recovery by 5% without raising cyanide use"
        assert result["kpi_parsed"] is not None
        assert isinstance(result["evidence"], list) and len(result["evidence"]) > 0
        assert isinstance(result["candidates"], list) and len(result["candidates"]) > 0
        assert isinstance(result["cited"], list) and len(result["cited"]) > 0
        assert isinstance(result["ranked"], list) and len(result["ranked"]) > 0
        assert isinstance(result["explained"], list) and len(result["explained"]) > 0
        assert result["export_path"] != ""
        assert isinstance(result["fe4_dropped"], list)

    def test_artifacts_persisted_in_store(self, config, fake_llm, fake_kg, in_memory_store):
        generator = FakeGenerator([make_valid_hypotheses()])

        orch = build_real_orchestrator(
            config,
            llm=fake_llm,
            kg=fake_kg,
            store=in_memory_store,
            retriever=FakeRetriever(),
            generator=generator,
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            trace_collector=FakeTraceCollector(),
        )

        result = orch.run("sess_artifacts", "Test query")
        run_id = result["run_id"]

        kpi_json = in_memory_store.load_artifact(run_id, "kpi_parse", "kpi_parsed")
        assert kpi_json is not None
        kpi_dict = json.loads(kpi_json)
        assert "goal" in kpi_dict

        evidence_json = in_memory_store.load_artifact(run_id, "retrieve", "evidence")
        assert evidence_json is not None

        candidates_json = in_memory_store.load_artifact(run_id, "generate", "candidates")
        assert candidates_json is not None

        cited_json = in_memory_store.load_artifact(run_id, "cite_bind", "cited")
        assert cited_json is not None

        ranked_json = in_memory_store.load_artifact(run_id, "score", "ranked")
        assert ranked_json is not None

        explained_json = in_memory_store.load_artifact(run_id, "explain", "explained")
        assert explained_json is not None

    def test_stage_states_all_done_or_error(self, config, fake_llm, fake_kg, in_memory_store):
        orch = build_real_orchestrator(
            config,
            llm=fake_llm,
            kg=fake_kg,
            store=in_memory_store,
            retriever=FakeRetriever(),
            generator=FakeGenerator([make_valid_hypotheses()]),
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            trace_collector=FakeTraceCollector(),
        )

        result = orch.run("sess_stages", "Test query")
        run_id = result["run_id"]

        all_stages = in_memory_store.get_all_stages(run_id)
        stage_names = [s["stage"] for s in all_stages]
        assert "kpi_parse" in stage_names
        assert "retrieve" in stage_names
        assert "generate" in stage_names
        assert "cite_bind" in stage_names
        assert "score" in stage_names
        assert "constraint_check" in stage_names
        assert "explain" in stage_names
        assert "export" in stage_names

        for stage_state in all_stages:
            assert stage_state["status"] in ("done", "error")

    def test_traces_recorded(self, config, fake_llm, fake_kg, in_memory_store):
        from hfabric.obs.traces import TraceCollector

        tc = TraceCollector(in_memory_store)

        orch = build_real_orchestrator(
            config,
            llm=fake_llm,
            kg=fake_kg,
            store=in_memory_store,
            retriever=FakeRetriever(),
            generator=FakeGenerator([make_valid_hypotheses()]),
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            trace_collector=tc,
        )
        orch.run("sess_traces", "Test query")

        cur = in_memory_store._conn.cursor()
        rows = cur.execute("SELECT * FROM traces").fetchall()
        assert len(rows) > 0


class TestJaccardDeterminism:
    def test_jaccard_equals_one_for_identical_runs(self, config, fake_llm, fake_kg, in_memory_store):
        def _run(session_id: str) -> list[Hypothesis]:
            orch = build_real_orchestrator(
                config,
                llm=fake_llm,
                kg=fake_kg,
                store=SessionStore(":memory:"),
                retriever=FakeRetriever(),
                generator=FakeGenerator([make_valid_hypotheses()]),
                citation=FakeCitation(coverage=1.0),
                scorer=FakeScorer(),
                explanation=FakeExplainer(),
                exporter=FakeExporter(),
                trace_collector=FakeTraceCollector(),
            )
            result = orch.run(session_id, "Test query")
            explained = result.get("explained", [])
            hypotheses: list[Hypothesis] = []
            for e in explained:
                hyp_dict = e.get("scored", {}).get("hypothesis", {})
                hypotheses.append(Hypothesis(**hyp_dict))
            return hypotheses

        run_a = _run("sess_a")
        run_b = _run("sess_b")

        score = jaccard_at_10(run_a, run_b)
        assert score >= 0.9


class TestKPIIncompleteGraceful:
    def test_retrieve_without_kpi_reports_incomplete(self, config, fake_kg, in_memory_store):
        bad_llm = MagicMock()
        structured = MagicMock()
        structured.invoke.side_effect = Exception("LLM unavailable")
        bad_llm.with_structured_output.return_value = structured

        orch = build_real_orchestrator(
            config,
            llm=bad_llm,
            kg=fake_kg,
            store=in_memory_store,
            retriever=FakeRetriever(),
            generator=FakeGenerator([make_valid_hypotheses()]),
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            trace_collector=FakeTraceCollector(),
        )

        result = orch.run("sess_err", "Test query")
        assert result["status"] == "incomplete"
        assert len(result.get("errors", [])) > 0


class TestRealComponentsIntegration:
    def test_real_citation_bind_works_in_orchestrator(
        self, config, fake_llm, fake_kg, in_memory_store
    ):
        orch = build_real_orchestrator(
            config,
            llm=fake_llm,
            kg=fake_kg,
            store=in_memory_store,
            retriever=FakeRetriever(),
            generator=FakeGenerator([make_valid_hypotheses()]),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            trace_collector=FakeTraceCollector(),
        )

        result = orch.run("sess_real_cite", "Test query")
        assert result["status"] == "complete"
        cited = result.get("cited", [])
        assert len(cited) > 0
        for c in cited:
            assert "cited_refs" in c

    def test_real_scorer_works_in_orchestrator(
        self, config, fake_llm, fake_kg, in_memory_store
    ):
        scores_config = MVPConfig(
            weight_novelty=0.3,
            weight_feasibility=0.4,
            weight_effect=0.3,
        )

        orch = build_real_orchestrator(
            scores_config,
            llm=fake_llm,
            kg=fake_kg,
            store=in_memory_store,
            retriever=FakeRetriever(),
            generator=FakeGenerator([make_valid_hypotheses()]),
            citation=FakeCitation(coverage=1.0),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            trace_collector=FakeTraceCollector(),
        )

        result = orch.run("sess_real_score", "Test query")
        assert result["status"] == "complete"
        ranked = result.get("ranked", [])
        assert len(ranked) > 0
        for r in ranked:
            assert "score" in r
            assert isinstance(r["score"], (int, float))
            assert "features" in r

    def test_real_exporter_writes_files(
        self, config, fake_llm, fake_kg, in_memory_store, tmp_path
    ):
        session_id = "sess_real_export"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            orch = build_real_orchestrator(
                config,
                llm=fake_llm,
                kg=fake_kg,
                store=in_memory_store,
                retriever=FakeRetriever(),
                generator=FakeGenerator([make_valid_hypotheses()]),
                citation=FakeCitation(coverage=1.0),
                scorer=FakeScorer(),
                explanation=FakeExplainer(),
                trace_collector=FakeTraceCollector(),
            )

            result = orch.run(session_id, "Test query")
            assert result["status"] == "complete"

            json_path = os.path.join("sessions", session_id, "export", "hypotheses.json")
            md_path = os.path.join("sessions", session_id, "export", "report.md")
            assert os.path.isfile(json_path)
            assert os.path.isfile(md_path)

            with open(md_path) as f:
                md_content = f.read()
            assert "Hypothesis Fabric" in md_content
            assert "Research Report" in md_content
        finally:
            os.chdir(orig_cwd)
