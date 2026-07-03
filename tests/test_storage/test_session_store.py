from __future__ import annotations

import tempfile
from pathlib import Path

from hfabric.schemas import TraceRecord
from hfabric.storage import SessionStore


def test_init_creates_tables() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        tables = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r[0] for r in tables if not r[0].startswith("sqlite_")}
        assert table_names == {"stage_state", "artifacts", "traces", "evals"}


def test_init_populates_stages() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        store.init("run-1")
        stages = store.get_all_stages("run-1")
        assert len(stages) == 8
        expected_stages = [
            "kpi_parse", "retrieve", "generate", "cite_bind",
            "score", "constraint_check", "explain", "export",
        ]
        assert [s["stage"] for s in stages] == expected_stages
        for s in stages:
            assert s["status"] == "pending"
            assert s["started_at"] is not None


def test_save_and_load_artifact_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        store.save_artifact("run-1", "score", "top_hypotheses", '{"count": 3}')
        result = store.load_artifact("run-1", "score", "top_hypotheses")
        assert result == '{"count": 3}'


def test_load_artifact_nonexistent() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        result = store.load_artifact("run-1", "score", "nonexistent")
        assert result is None


def test_artifact_upsert_overwrites() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        store.save_artifact("run-1", "score", "top_hypotheses", '{"count": 3}')
        store.save_artifact("run-1", "score", "top_hypotheses", '{"count": 5}')
        result = store.load_artifact("run-1", "score", "top_hypotheses")
        assert result == '{"count": 5}'


def test_save_trace_persists() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        trace = TraceRecord(
            run_id="run-1",
            stage="generate",
            slot="llm",
            token_in=500,
            token_out=200,
            latency_ms=1500.5,
            status="ok",
        )
        store.save_trace(trace)
        row = store._conn.execute(
            "SELECT run_id, stage, slot, token_in, token_out, latency_ms, status FROM traces"
        ).fetchone()
        assert row == ("run-1", "generate", "llm", 500, 200, 1500.5, "ok")


def test_set_stage_state_transitions() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        store.init("run-1")

        store.set_stage_state("run-1", "kpi_parse", "running")
        state = store.get_stage_state("run-1", "kpi_parse")
        assert state is not None
        assert state["status"] == "running"
        assert state["started_at"] is not None

        store.set_stage_state("run-1", "kpi_parse", "done")
        state = store.get_stage_state("run-1", "kpi_parse")
        assert state["status"] == "done"
        assert state["ended_at"] is not None


def test_set_stage_state_with_error() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        store.init("run-1")

        store.set_stage_state("run-1", "retrieve", "error", error="timeout")
        state = store.get_stage_state("run-1", "retrieve")
        assert state["status"] == "error"
        assert state["error"] == "timeout"
        assert state["ended_at"] is not None


def test_get_stage_state_nonexistent() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        result = store.get_stage_state("run-1", "kpi_parse")
        assert result is None


def test_get_all_stages_order() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        store.init("run-1")
        stages = store.get_all_stages("run-1")
        assert [s["id"] for s in stages] == list(range(1, 9))


def test_save_eval_stores_metrics() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        store.save_eval("run-1", "novelty_score", 0.85)
        store.save_eval("run-1", "feasibility_score", 0.72)
        rows = store._conn.execute(
            "SELECT metric, value FROM evals WHERE run_id = 'run-1' ORDER BY id"
        ).fetchall()
        assert rows == [("novelty_score", 0.85), ("feasibility_score", 0.72)]


def test_get_all_stages_only_for_run() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "session.db")
        store = SessionStore(db_path)
        store.init("run-1")
        store.init("run-2")
        stages_run1 = store.get_all_stages("run-1")
        stages_run2 = store.get_all_stages("run-2")
        assert len(stages_run1) == 8
        assert len(stages_run2) == 8
        for s in stages_run1:
            assert s["run_id"] == "run-1"
        for s in stages_run2:
            assert s["run_id"] == "run-2"
