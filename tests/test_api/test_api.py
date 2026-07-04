from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_orchestrator():
    orch = MagicMock()
    orch.run.return_value = {
        "run_id": "test_run_1",
        "ranked": [],
        "status": "done",
    }
    return orch


@pytest.fixture
def test_client(mock_orchestrator, tmp_path, monkeypatch):
    import hfabric.orchestrator.wiring as wiring
    from hfabric.api import app as app_mod

    monkeypatch.chdir(tmp_path)
    app_mod._sessions.clear()
    with patch.object(app_mod, "_build_session_index", lambda *a, **k: None), \
         patch.object(wiring, "build_real_orchestrator", return_value=mock_orchestrator):
        yield TestClient(app_mod.app)


class TestAPI:
    def test_health(self, test_client):
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_create_session(self, test_client):
        response = test_client.post("/sessions", json={"problem": "increase Au recovery", "constraints": ""})
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data

    def test_create_session_query_compat(self, test_client):
        response = test_client.post("/sessions", json={"query": "increase Au recovery"})
        assert response.status_code == 200
        assert "session_id" in response.json()

    def test_get_session(self, test_client):
        create_resp = test_client.post("/sessions", json={"problem": "test query"})
        session_id = create_resp.json()["session_id"]

        response = test_client.get(f"/sessions/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

    def test_run_pipeline(self, test_client):
        create_resp = test_client.post("/sessions", json={"problem": "test query"})
        session_id = create_resp.json()["session_id"]

        response = test_client.post(
            f"/sessions/{session_id}/run",
            json={"problem": "increase Au recovery by 5%", "constraints": "no cyanide"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data

    def test_get_results(self, test_client):
        create_resp = test_client.post("/sessions", json={"problem": "test query"})
        session_id = create_resp.json()["session_id"]
        test_client.post(f"/sessions/{session_id}/run", json={"problem": "x"})

        response = test_client.get(f"/sessions/{session_id}/results")
        assert response.status_code == 200

    def test_run_eval(self, test_client):
        create_resp = test_client.post("/sessions", json={"problem": "test query"})
        session_id = create_resp.json()["session_id"]
        test_client.post(f"/sessions/{session_id}/run", json={"problem": "x"})

        response = test_client.get(f"/sessions/{session_id}/eval")
        assert response.status_code == 200

    def test_404_unknown_session(self, test_client):
        response = test_client.get("/sessions/nonexistent")
        assert response.status_code == 404

    def test_list_sessions(self, test_client):
        test_client.post("/sessions", json={"problem": "a"})
        response = test_client.get("/sessions")
        assert response.status_code == 200
        assert len(response.json()["sessions"]) >= 1

    def test_upload_files(self, test_client):
        create_resp = test_client.post("/sessions", json={"problem": "p"})
        session_id = create_resp.json()["session_id"]
        response = test_client.post(
            f"/sessions/{session_id}/upload",
            files={"files": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert response.status_code == 200
        assert response.json()["count"] == 1

    def test_get_config(self, test_client):
        create_resp = test_client.post("/sessions", json={"problem": "p"})
        sid = create_resp.json()["session_id"]
        response = test_client.get(f"/sessions/{sid}/config")
        assert response.status_code == 200
        assert "weight_novelty" in response.json()

    def test_post_config(self, test_client):
        create_resp = test_client.post("/sessions", json={"problem": "p"})
        sid = create_resp.json()["session_id"]
        response = test_client.post(
            f"/sessions/{sid}/config",
            json={"weight_novelty": 0.5, "external_search": "none"},
        )
        assert response.status_code == 200
        assert response.json()["weight_novelty"] == 0.5

    def test_post_feedback(self, test_client):
        create_resp = test_client.post("/sessions", json={"problem": "p"})
        sid = create_resp.json()["session_id"]
        response = test_client.post(
            f"/sessions/{sid}/runs/r1/feedback",
            json={"claim": "test claim", "label": "accepted", "expert_id": "me"},
        )
        assert response.status_code == 200
        assert response.json()["saved"] is True

    def test_examples(self, test_client):
        response = test_client.get("/examples")
        assert response.status_code == 200
        assert "examples" in response.json()
