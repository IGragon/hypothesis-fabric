from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from hfabric.config import MVPConfig
from hfabric.orchestrator import Orchestrator
from hfabric.storage.session_store import SessionStore
from hfabric.schemas import EvidenceChunk, Hypothesis, KPIParsed, KPI, ScoredHypothesis

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
def protocols(temp_db, config):
    return {
        "llm": make_fake_llm(),
        "retriever": FakeRetriever(),
        "generator": FakeGenerator(responses=[make_valid_hypotheses()]),
        "citation": FakeCitation(coverage=1.0),
        "scorer": FakeScorer(),
        "explanation": FakeExplainer(),
        "exporter": FakeExporter(),
        "kg": FakeKG(),
        "store": temp_db,
        "trace_collector": FakeTraceCollector(),
        "config": config,
    }


class TestOrchestratorRerun:
    def test_rerun_produces_new_run_id(self, protocols):
        orch = Orchestrator(**protocols)
        protocols["store"].init("old_run_id")
        result = orch.rerun("session_1", "old_run_id", "generate")
        assert result["run_id"] is not None
        assert result["run_id"] != "old_run_id"

    def test_rerun_calls_store_init(self, protocols, temp_db):
        orch = Orchestrator(**protocols)
        protocols["store"].init("old_run")
        result = orch.rerun("session_1", "old_run", "generate")
        stages = protocols["store"].get_all_stages(result["run_id"])
        assert len(stages) == 8

    def test_rerun_invalid_stage_raises(self, protocols):
        orch = Orchestrator(**protocols)
        protocols["store"].init("run_1")
        with pytest.raises(ValueError):
            orch.rerun("session_1", "run_1", "invalid_stage")

    def test_rerun_applies_edited_artifacts_to_store(self, protocols):
        mock_store = MagicMock(wraps=protocols["store"])
        protocols["store"] = mock_store
        orch = Orchestrator(**protocols)
        mock_store.init("old_run")
        edited = {
            "retrieve": {"evidence": '{"edited": true}'},
        }
        orch.rerun("session_1", "old_run", "generate", edited_artifacts=edited)
        assert mock_store.save_artifact.called

    def test_rerun_loads_previous_artifacts(self, protocols):
        orch = Orchestrator(**protocols)
        protocols["store"].init("prev_run")

        first_result = orch.run("session_1", "increase Au recovery by 5%")
        prev_run_id = first_result["run_id"]

        result = orch.rerun("session_1", prev_run_id, "cite_bind")
        assert result["status"] in ("complete", "incomplete")
        assert result["run_id"] != prev_run_id

    def test_rerun_from_generate_is_default(self, protocols):
        orch = Orchestrator(**protocols)
        protocols["store"].init("old_run")
        result = orch.rerun("session_1", "old_run")
        assert result["run_id"] is not None
