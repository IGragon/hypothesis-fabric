from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _write_run_result(session_id: str, run_id: str, ranked=None):
    export_dir = os.path.join("sessions", session_id, "export")
    os.makedirs(export_dir, exist_ok=True)
    ranked = ranked if ranked is not None else []
    data = {
        "run_id": run_id,
        "session_id": session_id,
        "query": "increase Au recovery",
        "kpi": {
            "goal": "increase Au recovery",
            "kpi": {"metric": "Au recovery", "direction": "increase", "target": "5%"},
            "constraints": ["no cyanide increase"],
            "language": "en",
        },
        "ranked": ranked,
        "export_path": None,
        "status": "complete",
        "notes": [],
    }
    with open(os.path.join(export_dir, "hypotheses.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


@pytest.fixture
def client(tmp_path, monkeypatch):
    import hfabric.orchestrator.wiring as wiring
    from hfabric.api import app as app_mod

    orch = MagicMock()
    orch.run.return_value = {"run_id": "run-1", "ranked": [], "status": "done"}
    monkeypatch.chdir(tmp_path)
    app_mod._sessions.clear()
    with patch.object(app_mod, "_build_session_index", lambda *a, **k: None), \
         patch.object(wiring, "build_real_orchestrator", return_value=orch):
        yield TestClient(app_mod.app)


class TestEvalEndpoint:
    def test_run_eval_missing_result_returns_graceful(self, client):
        r = client.get("/sessions/sess-x/runs/run-y/eval")
        assert r.status_code == 404

    def test_run_eval_returns_real_metrics(self, client):
        _write_run_result("sess-1", "run-1", ranked=[])
        r = client.get("/sessions/sess-1/runs/run-1/eval")
        assert r.status_code == 200
        body = r.json()
        assert body["session_id"] == "sess-1"
        assert body["run_id"] == "run-1"
        assert "schema_validity" in body["metrics"]

    def test_latest_eval_alias_returns_graceful_without_result(self, client):
        r = client.post("/sessions", json={"problem": "x"})
        sid = r.json()["session_id"]
        client.post(f"/sessions/{sid}/run", json={"problem": "x"})
        r2 = client.get(f"/sessions/{sid}/eval")
        assert r2.status_code == 200
        assert "metrics" in r2.json()
        assert r2.json()["metrics"]["schema_validity"]["passed"] is True

    def test_latest_eval_alias_runs_real_eval_when_result_exists(self, client):
        r = client.post("/sessions", json={"problem": "increase Au recovery"})
        sid = r.json()["session_id"]
        _write_run_result(sid, "run-1", ranked=[])
        client.post(f"/sessions/{sid}/run", json={"problem": "increase Au recovery"})
        # ensure _sessions has the run entry so the alias picks run-1
        from hfabric.api import app as app_mod
        app_mod._sessions.setdefault(sid, {"runs": []})["runs"].append({"run_id": "run-1"})
        r2 = client.get(f"/sessions/{sid}/eval")
        assert r2.status_code == 200
        assert r2.json()["run_id"] == "run-1"