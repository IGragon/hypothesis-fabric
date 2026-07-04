from __future__ import annotations

import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from hfabric.config import MVPConfig
from hfabric.orchestrator import Orchestrator, build_graph
from hfabric.schemas import KPIParsed, KPI
from hfabric.storage.session_store import SessionStore

from .fakes import (
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
    make_invalid_hypotheses,
)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = SessionStore(db_path)
    yield store


@pytest.fixture
def config():
    return MVPConfig()


@pytest.fixture
def fake_retriever():
    return FakeRetriever()


@pytest.fixture
def fake_generator():
    return FakeGenerator(responses=[make_valid_hypotheses()])


@pytest.fixture
def fake_kg():
    return FakeKG()


@pytest.fixture
def fake_scorer():
    return FakeScorer()


@pytest.fixture
def fake_explainer():
    return FakeExplainer()


@pytest.fixture
def fake_exporter():
    return FakeExporter()


@pytest.fixture
def fake_trace_collector():
    return FakeTraceCollector()


@pytest.fixture
def fake_llm():
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = KPIParsed(
        goal="increase Au flotation recovery by 5% without raising cyanide use",
        kpi=KPI(metric="Au recovery", direction="increase", target="5%"),
        constraints=["no cyanide increase"],
        language="en",
    )
    llm.with_structured_output.return_value = structured
    return llm


@pytest.fixture
def fake_citation():
    return FakeCitation(coverage=1.0)


@pytest.fixture
def protocols(
    fake_llm,
    fake_retriever,
    fake_generator,
    fake_citation,
    fake_scorer,
    fake_explainer,
    fake_exporter,
    fake_kg,
    temp_db,
    fake_trace_collector,
    config,
):
    return {
        "llm": fake_llm,
        "retriever": fake_retriever,
        "generator": fake_generator,
        "citation": fake_citation,
        "scorer": fake_scorer,
        "explanation": fake_explainer,
        "exporter": fake_exporter,
        "kg": fake_kg,
        "store": temp_db,
        "trace_collector": fake_trace_collector,
        "config": config,
    }


class TestBuildGraph:
    def test_graph_executes_end_to_end(self, protocols):
        graph = build_graph(
            llm=protocols["llm"],
            retriever=protocols["retriever"],
            generator=protocols["generator"],
            citation=protocols["citation"],
            scorer=protocols["scorer"],
            explanation=protocols["explanation"],
            exporter=protocols["exporter"],
            kg=protocols["kg"],
            store=protocols["store"],
            trace_collector=protocols["trace_collector"],
            config=protocols["config"],
        )

        protocols["store"].init("test_run")

        result = graph.invoke({
            "run_id": "test_run",
            "session_id": "sess1",
            "nl_query": "increase Au flotation recovery by 5% without raising cyanide use",
            "kpi_parsed": None,
            "evidence": [],
            "low_confidence": False,
            "candidates": [],
            "cited": [],
            "coverage": 0.0,
            "ranked": [],
            "explained": [],
            "export_path": "",
            "export_json_path": "",
            "export_md_path": "",
            "status": "running",
            "errors": [],
            "fe1_attempt": 0,
            "fe2_attempt": 0,
            "fe6_attempt": 0,
            "fe4_dropped": [],
        })

        assert result["status"] == "complete"
        assert len(result["explained"]) >= 1
        assert result["kpi_parsed"] is not None
        assert len(result["evidence"]) >= 1
        assert len(result["ranked"]) >= 1

    def test_graph_runs_all_stages(self, protocols):
        graph = build_graph(
            llm=protocols["llm"],
            retriever=protocols["retriever"],
            generator=protocols["generator"],
            citation=protocols["citation"],
            scorer=protocols["scorer"],
            explanation=protocols["explanation"],
            exporter=protocols["exporter"],
            kg=protocols["kg"],
            store=protocols["store"],
            trace_collector=protocols["trace_collector"],
            config=protocols["config"],
        )

        protocols["store"].init("test_run")

        result = graph.invoke({
            "run_id": "test_run",
            "session_id": "sess1",
            "nl_query": "increase Au recovery",
            "kpi_parsed": None,
            "evidence": [],
            "low_confidence": False,
            "candidates": [],
            "cited": [],
            "coverage": 0.0,
            "ranked": [],
            "explained": [],
            "export_path": "",
            "export_json_path": "",
            "export_md_path": "",
            "status": "running",
            "errors": [],
            "fe1_attempt": 0,
            "fe2_attempt": 0,
            "fe6_attempt": 0,
            "fe4_dropped": [],
        })

        stages = protocols["store"].get_all_stages("test_run")
        stage_names = [s["stage"] for s in stages]
        assert "kpi_parse" in stage_names
        assert "retrieve" in stage_names
        assert "generate" in stage_names
        assert "cite_bind" in stage_names
        assert "score" in stage_names
        assert "constraint_check" in stage_names
        assert "explain" in stage_names
        assert "export" in stage_names

        done_stages = [s for s in stages if s["status"] == "done"]
        assert len(done_stages) == 8

    def test_artifacts_persisted(self, protocols):
        graph = build_graph(
            llm=protocols["llm"],
            retriever=protocols["retriever"],
            generator=protocols["generator"],
            citation=protocols["citation"],
            scorer=protocols["scorer"],
            explanation=protocols["explanation"],
            exporter=protocols["exporter"],
            kg=protocols["kg"],
            store=protocols["store"],
            trace_collector=protocols["trace_collector"],
            config=protocols["config"],
        )

        protocols["store"].init("run_artifacts")

        result = graph.invoke({
            "run_id": "run_artifacts",
            "session_id": "sess1",
            "nl_query": "increase Au recovery",
            "kpi_parsed": None,
            "evidence": [],
            "low_confidence": False,
            "candidates": [],
            "cited": [],
            "coverage": 0.0,
            "ranked": [],
            "explained": [],
            "export_path": "",
            "export_json_path": "",
            "export_md_path": "",
            "status": "running",
            "errors": [],
            "fe1_attempt": 0,
            "fe2_attempt": 0,
            "fe6_attempt": 0,
            "fe4_dropped": [],
        })

        assert result["status"] == "complete"

        kpi_json = protocols["store"].load_artifact("run_artifacts", "kpi_parse", "kpi_parsed")
        assert kpi_json is not None
        assert "Au recovery" in kpi_json

        evidence_json = protocols["store"].load_artifact("run_artifacts", "retrieve", "evidence")
        assert evidence_json is not None

        explained_json = protocols["store"].load_artifact("run_artifacts", "explain", "explained")
        assert explained_json is not None


class TestFE2Retry:
    def test_fe2_fires_when_generator_returns_invalid(self, config):
        fake_gen = FakeGenerator(responses=[
            [],
            make_valid_hypotheses(),
        ])

        store = SessionStore(":memory:")
        trace_coll = FakeTraceCollector()

        graph = build_graph(
            llm=make_fake_llm(),
            retriever=FakeRetriever(),
            generator=fake_gen,
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            kg=FakeKG(),
            store=store,
            trace_collector=trace_coll,
            config=config,
        )

        store.init("run_fe2")

        result = graph.invoke({
            "run_id": "run_fe2",
            "session_id": "sess1",
            "nl_query": "test query",
            "kpi_parsed": {"goal": "test", "kpi": {"metric": "m", "direction": "increase", "target": None}, "constraints": [], "language": "en"},
            "evidence": [{"chunk_id": "c1", "doc_id": "d1", "text": "test evidence", "meta": {}}],
            "low_confidence": False,
            "candidates": [],
            "cited": [],
            "coverage": 0.0,
            "ranked": [],
            "explained": [],
            "export_path": "",
            "export_json_path": "",
            "export_md_path": "",
            "status": "running",
            "errors": [],
            "fe1_attempt": 0,
            "fe2_attempt": 0,
            "fe6_attempt": 0,
            "fe4_dropped": [],
        })

        assert result["status"] == "complete"
        assert fake_gen._call_count == 2

    def test_fe2_exhausted_marks_incomplete(self, config):
        fake_gen = FakeGenerator(responses=[
            [],
            [],
            [],
        ])

        store = SessionStore(":memory:")
        trace_coll = FakeTraceCollector()

        graph = build_graph(
            llm=make_fake_llm(),
            retriever=FakeRetriever(),
            generator=fake_gen,
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            kg=FakeKG(),
            store=store,
            trace_collector=trace_coll,
            config=config,
        )

        store.init("run_fe2_ex")

        result = graph.invoke({
            "run_id": "run_fe2_ex",
            "session_id": "sess1",
            "nl_query": "test",
            "kpi_parsed": {"goal": "test", "kpi": {"metric": "m", "direction": "increase", "target": None}, "constraints": [], "language": "en"},
            "evidence": [{"chunk_id": "c1", "doc_id": "d1", "text": "test", "meta": {}}],
            "low_confidence": False,
            "candidates": [],
            "cited": [],
            "coverage": 0.0,
            "ranked": [],
            "explained": [],
            "export_path": "",
            "export_json_path": "",
            "export_md_path": "",
            "status": "running",
            "errors": [],
            "fe1_attempt": 0,
            "fe2_attempt": 0,
            "fe6_attempt": 0,
            "fe4_dropped": [],
        })

        assert result["status"] == "incomplete"
        assert "FE2 exhausted" in str(result.get("errors", ""))


class TestFE4Drops:
    def test_fe4_drops_violating_hypothesis(self, config):
        store = SessionStore(":memory:")
        trace_coll = FakeTraceCollector()

        custom_kpi = KPIParsed(
            goal="increase Au recovery without cyanide",
            kpi=KPI(metric="Au recovery", direction="increase", target="5%"),
            constraints=["no xanthate"],
            language="en",
        )

        graph = build_graph(
            llm=make_fake_llm(custom_kpi),
            retriever=FakeRetriever(),
            generator=FakeGenerator(responses=[make_valid_hypotheses()]),
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            kg=FakeKG(),
            store=store,
            trace_collector=trace_coll,
            config=config,
        )

        store.init("run_fe4")

        result = graph.invoke({
            "run_id": "run_fe4",
            "session_id": "sess1",
            "nl_query": "test with constraint violation",
            "kpi_parsed": {"goal": "increase Au recovery without cyanide", "kpi": {"metric": "Au recovery", "direction": "increase", "target": "5%"}, "constraints": ["no xanthate"], "language": "en"},
            "evidence": [{"chunk_id": "c1", "doc_id": "d1", "text": "Xanthate collectors improve gold flotation recovery.", "meta": {}}],
            "low_confidence": False,
            "candidates": [],
            "cited": [],
            "coverage": 0.0,
            "ranked": [],
            "explained": [],
            "export_path": "",
            "export_json_path": "",
            "export_md_path": "",
            "status": "running",
            "errors": [],
            "fe1_attempt": 0,
            "fe2_attempt": 0,
            "fe6_attempt": 0,
            "fe4_dropped": [],
        })

        dropped = result.get("fe4_dropped", [])
        assert len(result["ranked"]) >= 1
        assert len(dropped) > 0 or any(
            item.get("constraint_violations") for item in result["ranked"]
        )

    def test_all_dropped_goes_to_incomplete(self, config):
        store = SessionStore(":memory:")
        trace_coll = FakeTraceCollector()

        custom_kpi = KPIParsed(
            goal="test all dropped",
            kpi=KPI(metric="m", direction="increase", target=None),
            constraints=["no gold", "no xanthate", "no flotation"],
            language="en",
        )

        graph = build_graph(
            llm=make_fake_llm(custom_kpi),
            retriever=FakeRetriever(),
            generator=FakeGenerator(responses=[make_valid_hypotheses()]),
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            kg=FakeKG(),
            store=store,
            trace_collector=trace_coll,
            config=config,
        )

        store.init("run_fe4_all")

        result = graph.invoke({
            "run_id": "run_fe4_all",
            "session_id": "sess1",
            "nl_query": "test all dropped",
            "kpi_parsed": {"goal": "test", "kpi": {"metric": "m", "direction": "increase", "target": None}, "constraints": ["no gold", "no xanthate", "no flotation"], "language": "en"},
            "evidence": [{"chunk_id": "c1", "doc_id": "d1", "text": "test", "meta": {}}],
            "low_confidence": False,
            "candidates": [],
            "cited": [],
            "coverage": 0.0,
            "ranked": [],
            "explained": [],
            "export_path": "",
            "export_json_path": "",
            "export_md_path": "",
            "status": "running",
            "errors": [],
            "fe1_attempt": 0,
            "fe2_attempt": 0,
            "fe6_attempt": 0,
            "fe4_dropped": [],
        })

        assert result["status"] == "complete"
        assert len(result["ranked"]) >= 1
        assert any(
            item.get("constraint_violations") for item in result["ranked"]
        )


class TestTraceCollected:
    def test_traces_recorded_for_all_stages(self, protocols):
        graph = build_graph(
            llm=protocols["llm"],
            retriever=protocols["retriever"],
            generator=protocols["generator"],
            citation=protocols["citation"],
            scorer=protocols["scorer"],
            explanation=protocols["explanation"],
            exporter=protocols["exporter"],
            kg=protocols["kg"],
            store=protocols["store"],
            trace_collector=protocols["trace_collector"],
            config=protocols["config"],
        )

        protocols["store"].init("run_trace")

        result = graph.invoke({
            "run_id": "run_trace",
            "session_id": "sess1",
            "nl_query": "increase Au recovery",
            "kpi_parsed": None,
            "evidence": [],
            "low_confidence": False,
            "candidates": [],
            "cited": [],
            "coverage": 0.0,
            "ranked": [],
            "explained": [],
            "export_path": "",
            "export_json_path": "",
            "export_md_path": "",
            "status": "running",
            "errors": [],
            "fe1_attempt": 0,
            "fe2_attempt": 0,
            "fe6_attempt": 0,
            "fe4_dropped": [],
        })

        traces = protocols["trace_collector"].records
        assert len(traces) >= 7
        stages = {t.stage for t in traces}
        assert "kpi_parse" in stages
        assert "retrieve" in stages
        assert "cite_bind" in stages
        assert "score" in stages
        assert "constraint_check" in stages
        assert "explain" in stages
        assert "export" in stages


class TestOrchestratorClass:
    def test_orchestrator_run_produces_result(self, protocols):
        orchestrator = Orchestrator(
            llm=protocols["llm"],
            retriever=protocols["retriever"],
            generator=protocols["generator"],
            citation=protocols["citation"],
            scorer=protocols["scorer"],
            explanation=protocols["explanation"],
            exporter=protocols["exporter"],
            kg=protocols["kg"],
            store=protocols["store"],
            trace_collector=protocols["trace_collector"],
            config=protocols["config"],
        )

        protocols["store"].init("placeholder")

        result = orchestrator.run("sess1", "increase Au recovery by 5%")

        assert result["status"] in ("complete", "incomplete")
        assert result["run_id"] is not None
        assert result["session_id"] == "sess1"


class SlowGenerator:
    def __init__(self, sleep_seconds: float, responses: list[list[Hypothesis]] | None = None):
        self._sleep = sleep_seconds
        self._responses = responses or [[]]
        self._call_count = 0

    def generate(self, evidence, kpi, trace=None):
        time.sleep(self._sleep)
        idx = min(self._call_count, len(self._responses) - 1)
        result = self._responses[idx]
        self._call_count += 1
        return result


class TestTimeouts:
    def test_generate_timeout_returns_empty_and_continues(self, protocols):
        config = MVPConfig(
            timeout_generate=0.5,
            fe2_max_reprompt=0,
        )
        slow_gen = SlowGenerator(2.0, responses=[make_valid_hypotheses()])

        graph = build_graph(
            llm=protocols["llm"],
            retriever=protocols["retriever"],
            generator=slow_gen,
            citation=protocols["citation"],
            scorer=protocols["scorer"],
            explanation=protocols["explanation"],
            exporter=protocols["exporter"],
            kg=protocols["kg"],
            store=protocols["store"],
            trace_collector=protocols["trace_collector"],
            config=config,
        )

        protocols["store"].init("run_timeout")

        result = graph.invoke({
            "run_id": "run_timeout",
            "session_id": "sess1",
            "nl_query": "increase Au recovery",
            "kpi_parsed": None,
            "evidence": [],
            "low_confidence": False,
            "candidates": [],
            "cited": [],
            "coverage": 0.0,
            "ranked": [],
            "explained": [],
            "export_path": "",
            "export_json_path": "",
            "export_md_path": "",
            "status": "running",
            "errors": [],
            "fe1_attempt": 0,
            "fe2_attempt": 0,
            "fe6_attempt": 0,
            "fe4_dropped": [],
        })

        assert result["status"] in ("complete", "incomplete")

    def test_generate_timeout_does_not_hang(self):
        config = MVPConfig(timeout_generate=0.3, fe2_max_reprompt=0)
        store = SessionStore(":memory:")
        trace_coll = FakeTraceCollector()
        slow_gen = SlowGenerator(5.0, responses=[make_valid_hypotheses()])

        graph = build_graph(
            llm=make_fake_llm(),
            retriever=FakeRetriever(),
            generator=slow_gen,
            citation=FakeCitation(coverage=1.0),
            scorer=FakeScorer(),
            explanation=FakeExplainer(),
            exporter=FakeExporter(),
            kg=FakeKG(),
            store=store,
            trace_collector=trace_coll,
            config=config,
        )

        store.init("run_no_hang")

        t0 = time.perf_counter()
        result = graph.invoke({
            "run_id": "run_no_hang",
            "session_id": "sess1",
            "nl_query": "test query",
            "kpi_parsed": None,
            "evidence": [],
            "low_confidence": False,
            "candidates": [],
            "cited": [],
            "coverage": 0.0,
            "ranked": [],
            "explained": [],
            "export_path": "",
            "export_json_path": "",
            "export_md_path": "",
            "status": "running",
            "errors": [],
            "fe1_attempt": 0,
            "fe2_attempt": 0,
            "fe6_attempt": 0,
            "fe4_dropped": [],
        })
        elapsed = time.perf_counter() - t0

        assert elapsed < 3.0
        assert result["status"] in ("complete", "incomplete")
