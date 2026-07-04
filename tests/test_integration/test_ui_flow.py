from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_orch_with_result():
    orch = MagicMock()
    orch.run.return_value = {
        "run_id": "run_demo1",
        "status": "complete",
        "explained": [],
        "ranked": [],
        "export_json_path": "sessions/x/export/hypotheses.json",
        "export_md_path": "sessions/x/export/report.md",
    }
    return orch


@pytest.fixture
def client(mock_orch_with_result, tmp_path, monkeypatch):
    import hfabric.orchestrator.wiring as wiring
    from hfabric.api import app as app_mod

    monkeypatch.chdir(tmp_path)
    app_mod._sessions.clear()
    with patch.object(app_mod, "_build_session_index", lambda *a, **k: None), \
         patch.object(wiring, "build_real_orchestrator", return_value=mock_orch_with_result):
        yield TestClient(app_mod.app)


SAMPLE_RUN = {
    "run_id": "run_demo1",
    "session_id": "s1",
    "query": "increase Au recovery",
    "status": "complete",
    "kpi": {"goal": "increase Au recovery", "kpi": {"metric": "Au recovery", "direction": "increase", "target": "5%"}, "constraints": ["no cyanide increase"], "language": "en"},
    "ranked": [
        {
            "scored": {
                "hypothesis": {"claim": "Add xanthate to boost Au flotation", "mechanism": "chemisorption", "expected_effect": "+5% recovery", "evidence_refs": ["c1"]},
                "score": 0.82,
                "features": {"novelty": 0.4, "feasibility": 0.8, "effect": 0.7},
                "cited_refs": {
                    "c1": {"chunk_id": "c1", "doc_id": "doc1", "text": "Xanthate increases recovery", "meta": {"doc_id": "doc1"}},
                    "web:ab12": {"chunk_id": "web:ab12", "doc_id": "web:ab12", "text": "Best practices", "meta": {"url": "https://example.com/x", "title": "Example", "source": "web"}},
                },
            },
            "justification": "Supported by [c1].",
            "uncertainty": "Lab scale only [c1].",
            "verification_plan": "Run bench flotation [c1].",
            "graph_neighbourhood": ["gold -> Au recovery"],
            "effect_cause_examples": ["if xanthate then +5% [c1]"],
            "general_approach": "Collector addition [c1].",
            "actionable_now": "Test 50g/t [c1].",
            "why_it_matters": "Raises KPI [web:ab12].",
            "best_practices": "Standard [web:ab12].",
            "novelty": "Low [c1].",
            "risks": "Reagent cost [c1].",
            "section_citations": {"justification": ["c1"], "best_practices": ["web:ab12"]},
            "external_urls": ["https://example.com/x"],
        }
    ],
}


class TestUIFlow:
    def test_full_flow_create_upload_run_results(self, client, tmp_path):
        # 1. create session
        r = client.post("/sessions", json={"problem": "increase Au recovery by 5%", "constraints": "no cyanide"})
        assert r.status_code == 200
        sid = r.json()["session_id"]

        # 2. upload a file
        r = client.post(
            f"/sessions/{sid}/upload",
            files={"files": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert r.status_code == 200
        assert r.json()["count"] == 1

        # 3. run pipeline
        r = client.post(f"/sessions/{sid}/run", json={"problem": "increase Au recovery by 5%", "constraints": "no cyanide", "config": {"external_search": "none"}})
        assert r.status_code == 200
        rid = r.json()["run_id"]
        assert rid == "run_demo1"

        # 4. write a fake result file so GET /runs/{rid} works
        export_dir = os.path.join("sessions", sid, "export")
        os.makedirs(export_dir, exist_ok=True)
        import json
        with open(os.path.join(export_dir, "hypotheses.json"), "w") as f:
            json.dump(SAMPLE_RUN, f)
        with open(os.path.join(export_dir, "report.md"), "w") as f:
            f.write("# Report\n")

        # 5. GET run results
        r = client.get(f"/sessions/{sid}/runs/{rid}")
        assert r.status_code == 200
        data = r.json()
        assert len(data["ranked"]) == 1
        eh = data["ranked"][0]
        # 5 narrative sections present
        for section in ("effect_cause_examples", "general_approach", "actionable_now", "why_it_matters", "best_practices"):
            assert eh.get(section), f"section {section} empty"
        # at least one citation per key section
        cites = eh["section_citations"]
        assert "c1" in cites["justification"]
        assert "web:ab12" in cites["best_practices"]
        # external URL present
        assert "https://example.com/x" in eh["external_urls"]

    def test_graph_endpoint(self, client, tmp_path):
        sid = "s1"
        os.makedirs(os.path.join("sessions", sid, "export"), exist_ok=True)
        import json
        with open(os.path.join("sessions", sid, "export", "hypotheses.json"), "w") as f:
            json.dump(SAMPLE_RUN, f)
        r = client.get(f"/sessions/{sid}/runs/run_demo1/graph")
        assert r.status_code == 200
        g = r.json()
        assert len(g["nodes"]) > 0
        assert len(g["edges"]) > 0
        labels = {n["label"] for n in g["nodes"]}
        assert "Hypothesis" in labels

    def test_export_download(self, client, tmp_path):
        sid = "s1"
        os.makedirs(os.path.join("sessions", sid, "export"), exist_ok=True)
        with open(os.path.join("sessions", sid, "export", "report.md"), "w") as f:
            f.write("# Report\n\ntest")
        r = client.get(f"/sessions/{sid}/runs/run_demo1/export/download", params={"format": "md"})
        assert r.status_code == 200
        assert b"Report" in r.content
