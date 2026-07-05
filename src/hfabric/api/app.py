from __future__ import annotations

import json
import os
import shutil
import uuid
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from hfabric.obs.logging import configure_logging

configure_logging(os.environ.get("HFABRIC_LOG_LEVEL", "INFO"))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Hypothesis Fabric API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

_sessions: dict[str, dict[str, Any]] = {}


def _session_manager():
    from hfabric.session.manager import SessionManager

    return SessionManager()


def _build_session_index(config: Any, session_id: str) -> None:
    from hfabric.embeddings import SentenceTransformersProvider
    from hfabric.etl import ETL
    from hfabric.kg.client import MemgraphKG

    manager = _session_manager()
    raw_dir = manager.raw_files_dir(session_id)
    index_dir = manager.index_dir(session_id)
    if not manager.has_raw_files(session_id):
        print(f"[hfabric] _build_session_index: no raw files, skipping", flush=True)
        return
    print(f"[hfabric] _build_session_index: loading embeddings model", flush=True)
    embeddings = SentenceTransformersProvider(config.embeddings_model)
    try:
        print(f"[hfabric] _build_session_index: connecting to Memgraph", flush=True)
        kg = MemgraphKG(config.memgraph_uri)
        print(f"[hfabric] _build_session_index: Memgraph connected", flush=True)
    except Exception as e:
        print(f"[hfabric] _build_session_index: Memgraph failed: {e}", flush=True)
        kg = None
    etl = ETL(embeddings, kg, config)
    print(f"[hfabric] _build_session_index: building index (OCR + embeddings + FAISS + KG)", flush=True)
    etl.build_index(raw_dir, index_dir, session_id, "session")
    print(f"[hfabric] _build_session_index: DONE", flush=True)


def _config_dict(config: Any) -> dict[str, Any]:
    fields = (
        "provider", "model", "temperature", "external_search", "external_top_k",
        "weight_novelty", "weight_feasibility", "weight_effect",
        "weight_risk", "weight_realizability", "export_format",
        "enable_vlm", "enable_ocr", "vision_model",
    )
    return {f: getattr(config, f, None) for f in fields if hasattr(config, f)}


def _apply_overrides(config: Any, overrides: dict[str, Any]) -> Any:
    from hfabric.cli import build_config_from_env_and_overrides

    provider = overrides.get("provider")
    return build_config_from_env_and_overrides(provider_str=provider, overrides=overrides)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/sessions")
async def create_session(payload: dict[str, Any]):
    problem = payload.get("problem") or payload.get("query", "")
    constraints = payload.get("constraints", "")
    session_id = str(uuid.uuid4())[:8]
    meta = _session_manager().create_session(problem, constraints)
    session_id = meta["session_id"]
    _sessions[session_id] = {
        "session_id": session_id,
        "problem": problem,
        "constraints": constraints,
        "created_at": meta.get("created_at", ""),
        "runs": [],
    }
    return {"session_id": session_id, "meta": meta}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    meta = _session_manager().get_session(session_id)
    if meta is None and session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    if meta is None:
        return _sessions[session_id]
    meta["runs"] = _sessions.get(session_id, {}).get("runs", [])
    return meta


@app.get("/sessions")
async def list_sessions():
    manager = _session_manager()
    out: list[dict[str, Any]] = []
    if os.path.isdir(manager._base_dir):
        for name in sorted(os.listdir(manager._base_dir)):
            m = manager.get_session(name)
            if m is not None:
                out.append(m)
    return {"sessions": out}


@app.post("/sessions/{session_id}/upload")
async def upload_files(session_id: str, files: list[UploadFile] = File(...)):
    manager = _session_manager()
    if manager.get_session(session_id) is None and session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    raw_dir = manager.raw_files_dir(session_id)
    os.makedirs(raw_dir, exist_ok=True)
    saved: list[str] = []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        supported = (".pdf", ".xlsx", ".docx", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")
        if ext not in supported:
            continue
        dest = os.path.join(raw_dir, f.filename or f"file_{uuid.uuid4().hex[:6]}{ext}")
        with open(dest, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        saved.append(os.path.basename(dest))
    return {"session_id": session_id, "saved": saved, "count": len(saved)}


@app.get("/sessions/{session_id}/files/{filename:path}")
async def serve_session_file(session_id: str, filename: str):
    """Serve a raw uploaded file from a session's raw_files directory.

    Used by export reports and the UI to provide downloadable HTTP links to
    the source documents that back each evidence chunk (browsers block
    ``file://`` URLs for security).
    """
    safe = os.path.normpath(filename).lstrip("/\\")
    base = _session_manager().raw_files_dir(session_id)
    path = os.path.join(base, safe)
    if not os.path.isfile(path) or not os.path.abspath(path).startswith(os.path.abspath(base)):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=os.path.basename(path))


@app.post("/sessions/{session_id}/run")
async def run_pipeline(
    session_id: str, payload: dict[str, Any]
):
    import threading

    manager = _session_manager()
    meta = manager.get_session(session_id)
    if meta is None and session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    problem = payload.get("problem") or (meta or {}).get("nl_query") or ""
    constraints = payload.get("constraints") or (meta or {}).get("constraints") or ""
    config_overrides = payload.get("config", {}) or {}

    run_id = str(uuid.uuid4())[:8]
    entry = {
        "run_id": run_id,
        "problem": problem,
        "constraints": constraints,
        "status": "running",
    }
    sess = _sessions.setdefault(
        session_id,
        {
            "session_id": session_id,
            "problem": problem,
            "constraints": constraints,
            "created_at": "",
            "runs": [],
        },
    )
    sess["runs"].append(entry)
    manager.update_status(session_id, "running")

    thread = threading.Thread(
        target=_execute_run,
        args=(session_id, run_id, problem, constraints, config_overrides),
        daemon=True,
        name=f"hfabric-run-{run_id}",
    )
    thread.start()
    return {"status": "running", "run_id": run_id}


def _execute_run(
    session_id: str,
    run_id: str,
    problem: str,
    constraints: str,
    config_overrides: dict[str, Any],
) -> None:
    import logging
    import traceback

    logger = logging.getLogger("hfabric.api")
    print(f"[hfabric] _execute_run STARTED: session={session_id} run={run_id}", flush=True)
    query = problem
    if constraints:
        query = f"{problem}; constraints: {constraints}"

    from hfabric.config import MVPConfig
    from hfabric.orchestrator.wiring import build_real_orchestrator
    from hfabric.storage.session_store import SessionStore

    print(f"[hfabric] _execute_run: applying config overrides", flush=True)
    config = _apply_overrides(MVPConfig(), config_overrides)

    db_path = os.path.join("sessions", session_id, "session.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    print(f"[hfabric] _execute_run: initializing session store at {db_path}", flush=True)
    pre_store = SessionStore(db_path)
    pre_store.init(run_id)

    # Mark kpi_parse as running so the UI sees immediate progress
    pre_store.set_stage_state(run_id, "kpi_parse", "running")
    print(f"[hfabric] _execute_run: kpi_parse set to running in DB", flush=True)

    try:
        print(f"[hfabric] _execute_run: building session index", flush=True)
        logger.info("[run %s] building session index", run_id)
        _build_session_index(config, session_id)
        print(f"[hfabric] _execute_run: session index built", flush=True)
        logger.info("[run %s] session index built", run_id)
        pre_store.close()
        pre_store = None

        print(f"[hfabric] _execute_run: building orchestrator", flush=True)
        logger.info("[run %s] building orchestrator", run_id)
        orch = build_real_orchestrator(config, session_id=session_id)
        print(f"[hfabric] _execute_run: orchestrator built, starting pipeline", flush=True)
        logger.info("[run %s] orchestrator built, starting pipeline", run_id)
        result = orch.run(session_id, query, run_id=run_id)
        status = result.get("status", "unknown")
        print(f"[hfabric] _execute_run: pipeline finished: status={status}", flush=True)
        logger.info("[run %s] pipeline finished: status=%s", run_id, status)
    except Exception as exc:
        print(f"[hfabric] _execute_run: CRASHED: {exc}", flush=True)
        traceback.print_exc()
        logger.exception("[run %s] pipeline failed", run_id)
        status = "error"
        try:
            if pre_store is not None:
                pre_store.set_stage_state(run_id, "kpi_parse", "error", str(exc)[:500])
        except Exception:
            pass
        _sessions.get(session_id, {}).setdefault("runs", [])
        for r in _sessions[session_id]["runs"]:
            if r["run_id"] == run_id:
                r["status"] = "error"
                r["error"] = str(exc)
                break
        _session_manager().update_status(session_id, "error")
        return

    for r in _sessions.get(session_id, {}).get("runs", []):
        if r["run_id"] == run_id:
            r["status"] = status
            break
    _session_manager().update_status(session_id, status)


@app.post("/sessions/{session_id}/runs/{run_id}/rerun")
async def rerun_pipeline(session_id: str, run_id: str, payload: dict[str, Any]):
    manager = _session_manager()
    if manager.get_session(session_id) is None and session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    from_stage = payload.get("from_stage", "generate")
    edited_artifacts = payload.get("edited_artifacts")
    from hfabric.config import MVPConfig
    from hfabric.orchestrator.wiring import build_real_orchestrator

    config = MVPConfig()
    config = _apply_overrides(config, payload.get("config", {}) or {})
    orch = build_real_orchestrator(config, session_id=session_id)
    result = orch.rerun(session_id, run_id, from_stage, edited_artifacts)
    new_run_id = result.get("run_id", str(uuid.uuid4())[:8])
    sess = _sessions.setdefault(session_id, {
        "session_id": session_id, "problem": "", "constraints": "",
        "created_at": "", "runs": [],
    })
    sess["runs"].append({
        "run_id": new_run_id,
        "problem": payload.get("problem", ""),
        "constraints": payload.get("constraints", ""),
        "status": result.get("status", "unknown"),
    })
    return {"status": result.get("status"), "run_id": new_run_id}


def _load_run_result(session_id: str, run_id: str) -> dict | None:
    export_dir = _session_manager().export_dir(session_id)
    json_path = os.path.join(export_dir, "hypotheses.json")
    if not os.path.isfile(json_path):
        return None
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/sessions/{session_id}/runs/{run_id}")
async def get_run(session_id: str, run_id: str):
    data = _load_run_result(session_id, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run result not found")
    return data


@app.get("/sessions/{session_id}/runs/{run_id}/stages")
async def get_run_stages(session_id: str, run_id: str):
    from hfabric.storage.session_store import STAGES, SessionStore

    db_path = os.path.join("sessions", session_id, "session.db")
    if not os.path.isfile(db_path):
        return {
            "run_id": run_id,
            "stages": [{"stage": s, "status": "pending"} for s in STAGES],
            "artifacts": {},
        }
    store = SessionStore(db_path)
    stages = store.get_all_stages(run_id)
    if not stages:
        stages = [{"stage": s, "status": "pending"} for s in STAGES]
    artifacts: dict[str, dict[str, str]] = {}
    for s in stages:
        stage = s["stage"]
        for name in ("kpi_parsed", "evidence", "candidates", "cited", "ranked", "explained"):
            raw = store.load_artifact(run_id, stage, name)
            if raw is not None:
                artifacts.setdefault(stage, {})[name] = raw
    return {"run_id": run_id, "stages": stages, "artifacts": artifacts}


@app.get("/sessions/{session_id}/runs/{run_id}/graph")
async def get_run_graph(session_id: str, run_id: str):
    data = _load_run_result(session_id, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run result not found")
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for eh in data.get("ranked", []):
        scored = eh.get("scored", {})
        hyp = scored.get("hypothesis", {})
        claim = hyp.get("claim", "")[:60]
        hyp_node = f"hyp:{claim}"
        nodes[hyp_node] = {"id": hyp_node, "label": "Hypothesis", "name": claim, "score": scored.get("score", 0)}
        for cid, chunk in scored.get("cited_refs", {}).items():
            url = chunk.get("meta", {}).get("url")
            title = chunk.get("meta", {}).get("title") or chunk.get("doc_id", cid)
            node_id = url or cid
            label = "WebSource" if url else "Evidence"
            if node_id not in nodes:
                nodes[node_id] = {"id": node_id, "label": label, "name": title, "url": url or ""}
            edges.append({"source": hyp_node, "target": node_id, "rel": "cites"})
        for nb in eh.get("graph_neighbourhood", []):
            parts = nb.split("->")
            if len(parts) == 2:
                src = parts[0].strip().split(":")[-1].strip()
                dst = parts[1].strip()
                sid, did = f"kg:{src}", f"kg:{dst}"
                nodes.setdefault(sid, {"id": sid, "label": "KG", "name": src})
                nodes.setdefault(did, {"id": did, "label": "KG", "name": dst})
                edges.append({"source": sid, "target": did, "rel": "influences"})
    return {"nodes": list(nodes.values()), "edges": edges}


@app.post("/sessions/{session_id}/runs/{run_id}/export")
async def export_run(session_id: str, run_id: str, payload: dict[str, Any] = None):
    payload = payload or {}
    fmt = payload.get("format", "md")
    if fmt not in ("md", "json", "docx", "pdf", "csv"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")
    _ensure_export_artifacts(session_id, run_id, fmt)
    data = _load_run_result(session_id, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run result not found")
    export_dir = _session_manager().export_dir(session_id)
    names = {
        "md": "report.md", "json": "hypotheses.json", "docx": "report.docx",
        "pdf": "report.pdf", "csv": "hypotheses.csv",
    }
    path = os.path.join(export_dir, names[fmt])
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"{names[fmt]} could not be generated")
    return {"path": path, "format": fmt}


def _ensure_export_artifacts(session_id: str, run_id: str, fmt: str) -> None:
    from hfabric.schemas import RunResult

    export_dir = _session_manager().export_dir(session_id)
    name = {"pdf": "report.pdf", "csv": "hypotheses.csv", "docx": "report.docx"}.get(fmt)
    if name is None:
        return
    target = os.path.join(export_dir, name)
    if os.path.isfile(target):
        return
    json_path = os.path.join(export_dir, "hypotheses.json")
    if not os.path.isfile(json_path):
        return
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        result = RunResult.model_validate(data)
    except Exception:
        return
    try:
        if fmt == "pdf":
            from hfabric.export.pdf_writer import write_pdf
            write_pdf(result, session_id)
        elif fmt == "csv":
            from hfabric.export.csv_writer import write_csv
            write_csv(result, session_id)
        elif fmt == "docx":
            from hfabric.export.docx_writer import write_docx
            write_docx(result, session_id)
    except Exception:
        pass


@app.get("/sessions/{session_id}/runs/{run_id}/export/download")
async def download_export(session_id: str, run_id: str, format: str = "md"):
    if format not in ("md", "json", "docx", "pdf", "csv"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
    _ensure_export_artifacts(session_id, run_id, format)
    export_dir = _session_manager().export_dir(session_id)
    names = {
        "md": "report.md", "json": "hypotheses.json", "docx": "report.docx",
        "pdf": "report.pdf", "csv": "hypotheses.csv",
    }
    name = names.get(format, "report.md")
    path = os.path.join(export_dir, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"{name} not found")
    media = {
        "md": "text/markdown", "json": "application/json",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf", "csv": "text/csv",
    }
    return FileResponse(path, media_type=media.get(format, "text/plain"), filename=name)


@app.get("/sessions/{session_id}/results")
async def get_results(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "runs": _sessions[session_id].get("runs", [])}


@app.get("/sessions/{session_id}/latest")
async def get_latest_result(session_id: str):
    """Return the latest persisted run result for a session.

    The export writer saves ``hypotheses.json`` directly under
    ``sessions/<sid>/export/`` (overwriting on each run), so the latest result
    is always whatever is on disk — independent of the in-memory ``_sessions``
    registry (which is lost on restart).  ``run_id`` is read from the file's
    ``run_id`` field when present.
    """
    data = _load_run_result(session_id, "__latest__")
    if data is None:
        raise HTTPException(status_code=404, detail="No run result found for session")
    return data


@app.get("/sessions/{session_id}/runs/{run_id}/eval")
async def run_eval(session_id: str, run_id: str):
    data = _load_run_result(session_id, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run result not found")
    from hfabric.obs.evals import run_evals
    from hfabric.schemas import RunResult, ScoredHypothesis

    try:
        result = RunResult.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cannot parse run result: {exc}") from exc

    hypotheses: list[ScoredHypothesis] = [eh.scored for eh in result.ranked]
    metrics = run_evals(
        session_id=session_id,
        hypotheses=hypotheses or [eh.scored for eh in result.ranked] or [],
        constraints=result.kpi.constraints,
    )
    if not hypotheses:
        metrics["schema_validity"] = {"passed": True, "failed_count": 0, "violations": []}
    return {"session_id": session_id, "run_id": run_id, "metrics": metrics}


@app.get("/sessions/{session_id}/eval")
async def run_eval_latest(session_id: str):
    sess = _sessions.get(session_id)
    runs = sess.get("runs", []) if sess else []
    run_id = runs[-1].get("run_id") if runs else None
    empty = {
        "session_id": session_id,
        "run_id": run_id,
        "metrics": {"schema_validity": {"passed": True, "failed_count": 0, "violations": []}},
    }
    if not run_id:
        empty["run_id"] = None
        return empty
    if _load_run_result(session_id, run_id) is None:
        return empty
    return await run_eval(session_id, run_id)


@app.get("/sessions/{session_id}/config")
async def get_session_config(session_id: str):
    from hfabric.config import MVPConfig
    return _config_dict(MVPConfig())


@app.post("/sessions/{session_id}/config")
async def set_session_config(session_id: str, payload: dict[str, Any]):
    from hfabric.config import MVPConfig
    config = MVPConfig()
    config = _apply_overrides(config, payload)
    return _config_dict(config)


@app.post("/sessions/{session_id}/runs/{run_id}/feedback")
async def post_feedback(session_id: str, run_id: str, payload: dict[str, Any]):
    from hfabric.storage.feedback_store import FeedbackStore

    db_path = os.path.join("sessions", session_id, "feedback.db")
    store = FeedbackStore(db_path)
    claim = payload.get("claim", "")
    label = payload.get("label", "")
    expert_id = payload.get("expert_id", "ui")
    comment = payload.get("comment", "")
    if label not in ("accepted", "rejected", "adjusted"):
        raise HTTPException(status_code=400, detail="label must be accepted/rejected/adjusted")

    features = payload.get("features")
    if not features:
        data = _load_run_result(session_id, run_id)
        if data is not None:
            for eh in data.get("ranked", []):
                scored = eh.get("scored", {})
                hyp = scored.get("hypothesis", {})
                if hyp.get("claim", "") == claim:
                    features = scored.get("features")
                    break

    label_id = store.save_label(
        run_id, claim, label, expert_id, comment,
        features=features if isinstance(features, dict) else None,
    )
    return {"id": label_id, "saved": True, "features_attached": bool(features)}


@app.get("/sessions/{session_id}/runs/{run_id}/feedback")
async def get_feedback(session_id: str, run_id: str):
    from hfabric.storage.feedback_store import FeedbackStore

    db_path = os.path.join("sessions", session_id, "feedback.db")
    if not os.path.isfile(db_path):
        return {"labels": []}
    store = FeedbackStore(db_path)
    all_labels = store.get_all_labels()
    return {"labels": [l for l in all_labels if l["run_id"] == run_id]}


@app.get("/examples")
async def list_examples():
    base = "additional_material"
    out: list[dict[str, Any]] = []
    if not os.path.isdir(base):
        return {"examples": out}
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not os.path.isdir(d) or not name.startswith("Пример"):
            continue
        files = sorted(os.listdir(d)) if os.path.isdir(d) else []
        output_text = _extract_example_output(d, files)
        output_file = next((f for f in files if f.lower().endswith(".docx")), "")
        out.append({
            "name": name,
            "dir": d,
            "files": files,
            "problem": f"Анализ гипотез и хвостов для {name}",
            "constraints": "Доступное сырьё и оборудование НОФ; нормативные документы",
            "output_file": output_file,
            "output_text": output_text,
        })
    return {"examples": out}


def _extract_example_output(dir_path: str, files: list[str]) -> str:
    docx_files = [f for f in files if f.lower().endswith(".docx") and "гипотез" in f.lower()]
    if not docx_files:
        return ""
    try:
        import docx

        doc = docx.Document(os.path.join(dir_path, docx_files[0]))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except Exception:
        return ""


@app.post("/sessions/{session_id}/runs/{run_id}/export/jira")
async def export_jira(session_id: str, run_id: str, payload: dict[str, Any] = None):
    payload = payload or {}
    data = _load_run_result(session_id, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run result not found")
    from hfabric.export.jira import JiraExporter

    base_url = os.environ.get("JIRA_BASE_URL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")
    project = os.environ.get("JIRA_PROJECT_KEY", "HF")
    email = os.environ.get("JIRA_EMAIL", "")
    exporter = JiraExporter(base_url=base_url, api_token=token, project_key=project, email=email)
    created: list[dict[str, Any]] = []
    for eh in data.get("ranked", []):
        claim = eh.get("scored", {}).get("hypothesis", {}).get("claim", "")
        ext_id = f"{run_id}:{abs(hash(claim)) % 10**10}"
        r = exporter.create_task(
            summary=claim[:200],
            description=eh.get("justification", "") + "\n" + eh.get("verification_plan", ""),
            external_id=ext_id,
        )
        if r:
            created.append(r)
    return {"exported": created, "count": len(created)}


@app.post("/sessions/{session_id}/runs/{run_id}/export/youtrack")
async def export_youtrack(session_id: str, run_id: str, payload: dict[str, Any] = None):
    payload = payload or {}
    data = _load_run_result(session_id, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run result not found")
    from hfabric.export.youtrack import YouTrackExporter

    base_url = os.environ.get("YOUTRACK_BASE_URL", "")
    token = os.environ.get("YOUTRACK_TOKEN", "")
    project = os.environ.get("YOUTRACK_PROJECT_ID", "0-0")
    exporter = YouTrackExporter(base_url=base_url, token=token, project_id=project)
    created: list[dict[str, Any]] = []
    for eh in data.get("ranked", []):
        claim = eh.get("scored", {}).get("hypothesis", {}).get("claim", "")
        ext_id = f"{run_id}:{abs(hash(claim)) % 10**10}"
        r = exporter.create_task(
            summary=claim[:200],
            description=eh.get("justification", "") + "\n" + eh.get("verification_plan", ""),
            external_id=ext_id,
        )
        if r:
            created.append(r)
    return {"exported": created, "count": len(created)}


from pathlib import Path as _Path

_UI_DIR = _Path(__file__).resolve().parents[3] / "hypothesis-fabric-ui"
if _UI_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
