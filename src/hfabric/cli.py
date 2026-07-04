from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from hfabric.config import MVPConfig, ProviderType
from hfabric.schemas import (
    ExplainedHypothesis,
    Hypothesis,
    KPIParsed,
    ScoredHypothesis,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hypothesis Fabric — metallurgy hypothesis generation"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    index_kb = sub.add_parser("index-kb", help="Build/refresh global KB index")
    index_kb.set_defaults(func=cmd_index_kb)

    new_ = sub.add_parser("new", help="Create a new session")
    new_.add_argument("query", type=str, help="NL query for the session")
    new_.set_defaults(func=cmd_new)

    run_ = sub.add_parser("run", help="Execute a run pipeline")
    run_.add_argument("session_id", type=str, help="Session ID")
    run_.add_argument("query", type=str, help="NL query for the run")
    run_.add_argument("--provider", type=str, default=None,
                      choices=[p.value for p in ProviderType],
                      help="LLM provider (default: yandex)")
    run_.add_argument("--format", choices=["json", "docx", "pdf", "csv"], default="json",
                      help="Export format (default: json)")
    run_.add_argument("--jira", action="store_true", default=False,
                      help="Export hypotheses to Jira after run")
    run_.add_argument("--youtrack", action="store_true", default=False,
                      help="Export hypotheses to YouTrack after run")
    run_.set_defaults(func=cmd_run)

    eval_ = sub.add_parser("eval", help="Run evals on a session")
    eval_.add_argument("session_id", type=str, help="Session ID")
    eval_.add_argument("--provider", type=str, default=None,
                       choices=[p.value for p in ProviderType],
                       help="LLM provider (default: yandex)")
    eval_.set_defaults(func=cmd_eval)

    rerun_ = sub.add_parser("rerun", help="Re-run a pipeline stage")
    rerun_.add_argument("session_id", type=str, help="Session ID")
    rerun_.add_argument("run_id", type=str, help="Run ID to load state from")
    rerun_.add_argument("--from-stage", type=str, default="generate", help="Stage to restart from")
    rerun_.add_argument("--provider", type=str, default=None,
                        choices=[p.value for p in ProviderType],
                        help="LLM provider (default: yandex)")
    rerun_.set_defaults(func=cmd_rerun)

    serve_ = sub.add_parser("serve", help="Start FastAPI server")
    serve_.add_argument("--port", type=int, default=8000, help="Port to listen on")
    serve_.set_defaults(func=cmd_serve)

    serve_ui = sub.add_parser("serve-ui", help="Start Streamlit UI")
    serve_ui.add_argument("--port", type=int, default=8501, help="Port to listen on")
    serve_ui.set_defaults(func=cmd_serve_ui)

    serve_pg = sub.add_parser("serve-playground", help="Start Streamlit retrieval playground")
    serve_pg.add_argument("--port", type=int, default=8502, help="Port to listen on")
    serve_pg.set_defaults(func=cmd_serve_playground)

    return parser


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass


def _configure_logging() -> None:
    from hfabric.obs.logging import configure_logging

    configure_logging(os.environ.get("HFABRIC_LOG_LEVEL", "INFO"))


def _provider_from_env_or_arg(provider_str: str | None) -> ProviderType | None:
    if provider_str:
        return ProviderType(provider_str)
    env_prov = os.environ.get("HFABRIC_PROVIDER")
    if env_prov:
        try:
            return ProviderType(env_prov)
        except ValueError:
            return None
    return None


def build_config_from_env_and_overrides(
    provider_str: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> MVPConfig:
    provider = _provider_from_env_or_arg(provider_str)
    config = MVPConfig(provider=provider) if provider is not None else MVPConfig()
    overrides = overrides or {}
    weight_fields = (
        "weight_novelty", "weight_feasibility", "weight_effect",
        "weight_risk", "weight_realizability",
        "weight_evidence", "weight_violation",
    )
    for f in weight_fields:
        if f in overrides and overrides[f] is not None:
            setattr(config, f, float(overrides[f]))
    for f in (
        "model", "temperature", "external_search", "external_top_k",
        "export_format", "enable_vlm", "enable_ocr",
        "timeout_explain", "timeout_explain_per_hypothesis",
        "max_explain_hypotheses",
    ):
        if f in overrides and overrides[f] is not None:
            setattr(config, f, overrides[f])
    if "provider" in overrides and overrides.get("provider") is not None:
        try:
            config.provider = ProviderType(overrides["provider"])
            if overrides.get("model") is None:
                config.model = None
                config.__post_init__()
        except ValueError:
            pass
    return config


def _load_config(provider_str: str | None = None) -> MVPConfig:
    return build_config_from_env_and_overrides(provider_str=provider_str)


def _build_kb_index(config: MVPConfig) -> Any:
    from hfabric.embeddings import SentenceTransformersProvider
    from hfabric.etl import ETL
    from hfabric.kg.client import MemgraphKG

    embeddings = SentenceTransformersProvider(config.embeddings_model)
    kg = MemgraphKG(config.memgraph_uri)
    etl = ETL(embeddings, kg, config)
    return etl


def cmd_index_kb(args: argparse.Namespace) -> None:
    _load_env()
    config = MVPConfig()
    kb_dir = "knowledge_base"
    index_dir = "knowledge_base/.index/kb"

    if not os.path.isdir(kb_dir):
        print(f"Error: knowledge_base/ directory not found at {kb_dir}", file=sys.stderr)
        sys.exit(1)

    pdfs = [f for f in os.listdir(kb_dir) if f.lower().endswith(".pdf")]
    if not pdfs:
        print(f"Error: no PDF files found in {kb_dir}/", file=sys.stderr)
        sys.exit(1)

    print(f"Building KB index from {len(pdfs)} PDF(s)...")
    etl = _build_kb_index(config)
    artifact = etl.build_index(kb_dir, index_dir, "kb", "kb")
    print(f"KB index built: {artifact.num_chunks} chunks at {index_dir}")


def cmd_new(args: argparse.Namespace) -> None:
    from hfabric.session.manager import SessionManager

    manager = SessionManager()
    meta = manager.create_session(args.query)
    sid = meta["session_id"]
    print(f"Session created: {sid}")
    print(f"  Query: {args.query}")
    print(f"  Raw files dir: sessions/{sid}/raw_files/")
    print("Place PDF files in raw_files/ before running.")


def _build_session_index(config: MVPConfig, session_id: str) -> None:
    from hfabric.session.manager import SessionManager

    manager = SessionManager()
    raw_dir = manager.raw_files_dir(session_id)
    index_dir = manager.index_dir(session_id)

    if not manager.has_raw_files(session_id):
        return

    from hfabric.embeddings import SentenceTransformersProvider
    from hfabric.etl import ETL
    from hfabric.kg.client import MemgraphKG

    embeddings = SentenceTransformersProvider(config.embeddings_model)
    kg = MemgraphKG(config.memgraph_uri)
    etl = ETL(embeddings, kg, config)

    print(f"Building session index from raw_files/...")
    artifact = etl.build_index(raw_dir, index_dir, session_id, "session")
    print(f"Session index built: {artifact.num_chunks} chunks")


def _print_results(state: dict) -> None:
    notified = False
    errors = state.get("errors", [])
    if errors:
        print(f"\n{'='*70}")
        print(f"Pipeline errors ({len(errors)}):")
        print(f"{'='*70}")
        for e in errors:
            print(f"  - {e}")
        notified = True

    explained_raw = state.get("explained", [])
    if not explained_raw:
        if not notified:
            print("No hypotheses generated.")
        status = state.get("status", "unknown")
        print(f"Status: {status}")
        return

    print(f"\n{'='*70}")
    print(f"Ranked Hypotheses ({len(explained_raw)} total)")
    print(f"{'='*70}\n")

    for i, e_dict in enumerate(explained_raw, 1):
        scored_dict = e_dict.get("scored", {})
        hyp_dict = scored_dict.get("hypothesis", {})
        score = scored_dict.get("score", 0.0)
        features = scored_dict.get("features", {})

        print(f"#{i}  Score: {score:.3f}")
        print(f"  Claim: {hyp_dict.get('claim', 'N/A')}")
        print(f"  Mechanism: {hyp_dict.get('mechanism', 'N/A')}")
        print(f"  Expected effect: {hyp_dict.get('expected_effect', 'N/A')}")
        print(f"  Evidence refs: {hyp_dict.get('evidence_refs', [])}")
        print(f"  Features: novelty={features.get('novelty', 0):.2f}, "
              f"feasibility={features.get('feasibility', 0):.2f}, "
              f"effect={features.get('effect', 0):.2f}")
        print(f"  Justification: {e_dict.get('justification', 'N/A')}")
        print(f"  Uncertainty: {e_dict.get('uncertainty', 'N/A')}")
        print(f"  Verification: {e_dict.get('verification_plan', 'N/A')}")
        nb = e_dict.get("graph_neighbourhood", [])
        if nb:
            print(f"  KG neighbourhood:")
            for line in nb[:5]:
                print(f"    - {line}")
            if len(nb) > 5:
                print(f"    ... ({len(nb) - 5} more)")
        print()

    print(f"Status: {state.get('status', 'unknown')}")
    json_path = state.get("export_json_path", "")
    md_path = state.get("export_md_path", "")
    if json_path:
        print(f"Export JSON: {json_path}")
    if md_path:
        print(f"Export MD:   {md_path}")


def cmd_run(args: argparse.Namespace) -> None:
    _load_env()
    config = _load_config(args.provider)
    config.export_format = args.format
    session_id = args.session_id

    from hfabric.session.manager import SessionManager

    manager = SessionManager()
    meta = manager.get_session(session_id)
    if meta is None:
        print(f"Error: session '{session_id}' not found.", file=sys.stderr)
        sys.exit(1)

    _build_session_index(config, session_id)

    from hfabric.orchestrator.wiring import build_real_orchestrator

    print(f"Running pipeline for session {session_id}...")
    orchestrator = build_real_orchestrator(config, session_id=session_id)
    state = orchestrator.run(session_id, args.query)

    manager.update_status(session_id, state.get("status", "unknown"))
    _print_results(state)

    if args.jira:
        _export_to_tracker(session_id, "jira")
    if args.youtrack:
        _export_to_tracker(session_id, "youtrack")


def _export_to_tracker(session_id: str, tracker: str) -> None:
    data = _load_run_result(session_id)
    if data is None:
        print(f"{tracker} export skipped: no run result found")
        return
    run_id = data.get("run_id", "")
    if tracker == "jira":
        from hfabric.export.jira import JiraExporter
        exporter = JiraExporter(
            base_url=os.environ.get("JIRA_BASE_URL", ""),
            api_token=os.environ.get("JIRA_API_TOKEN", ""),
            project_key=os.environ.get("JIRA_PROJECT_KEY", "HF"),
            email=os.environ.get("JIRA_EMAIL", ""),
        )
        key = "key"
    else:
        from hfabric.export.youtrack import YouTrackExporter
        exporter = YouTrackExporter(
            base_url=os.environ.get("YOUTRACK_BASE_URL", ""),
            token=os.environ.get("YOUTRACK_TOKEN", ""),
            project_id=os.environ.get("YOUTRACK_PROJECT_ID", "0-0"),
        )
        key = "idReadable"
    created = 0
    mocked = False
    for eh in data.get("ranked", []):
        claim = eh.get("scored", {}).get("hypothesis", {}).get("claim", "")
        ext_id = f"{run_id}:{abs(hash(claim)) % 10**10}"
        r = exporter.create_task(
            summary=claim[:200],
            description=eh.get("justification", "") + "\n" + eh.get("verification_plan", ""),
            external_id=ext_id,
        )
        if r:
            created += 1
            if r.get("status") == "mocked":
                mocked = True
    note = " (mocked — set env vars to enable real export)" if mocked else ""
    print(f"{tracker} export: {created} tasks created{note}")


def _load_run_result(session_id: str) -> dict | None:
    from hfabric.session.manager import SessionManager

    manager = SessionManager()
    json_path = os.path.join(manager.export_dir(session_id), "hypotheses.json")
    if not os.path.isfile(json_path):
        return None
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def cmd_eval(args: argparse.Namespace) -> None:
    _load_env()
    config = _load_config(args.provider)
    session_id = args.session_id

    from hfabric.session.manager import SessionManager

    manager = SessionManager()
    meta = manager.get_session(session_id)
    if meta is None:
        print(f"Error: session '{session_id}' not found.", file=sys.stderr)
        sys.exit(1)

    result_data = _load_run_result(session_id)
    if result_data is None:
        print(f"Error: no export found for session '{session_id}'. "
              f"Run 'hfabric run {session_id} \"<query>\"' first.", file=sys.stderr)
        sys.exit(1)

    ranked_raw = result_data.get("ranked", [])
    hypotheses: list[Hypothesis] = []
    scored: list[ScoredHypothesis] = []
    for item in ranked_raw:
        scored_dict = item.get("scored", {})
        hyp = Hypothesis(**scored_dict.get("hypothesis", {}))
        hypotheses.append(hyp)
        cited = {
            k: v for k, v in scored_dict.get("cited_refs", {}).items()
        }
        scored.append(ScoredHypothesis(
            hypothesis=hyp,
            score=scored_dict.get("score", 0.0),
            features=scored_dict.get("features", {}),
            cited_refs=cited,
        ))

    kpi_dict = result_data.get("kpi", {})
    constraints = kpi_dict.get("constraints", [])

    from hfabric.obs.evals import run_evals

    evals = run_evals(session_id, scored, constraints)

    print(f"\n{'='*70}")
    print(f"Evaluation Results for session {session_id}")
    print(f"{'='*70}\n")

    for metric, result in evals.items():
        if isinstance(result, dict):
            passed = result.get("passed", result.get("pass_count", 0))
            print(f"  {metric}: {result}")
        else:
            print(f"  {metric}: {result}")

    print("\n  Re-running pipeline for Jaccard@10 determinism check...")
    from hfabric.orchestrator.wiring import build_real_orchestrator

    orchestrator = build_real_orchestrator(config, session_id=session_id)
    state = orchestrator.run(session_id, result_data.get("query", ""))

    rerun_hyps: list[Hypothesis] = []
    for e_dict in state.get("explained", []):
        scored_dict = e_dict.get("scored", {})
        rerun_hyps.append(Hypothesis(**scored_dict.get("hypothesis", {})))

    from hfabric.obs.evals import jaccard_at_10

    score = jaccard_at_10(hypotheses, rerun_hyps)
    print(f"\n  Jaccard@10: {score:.3f}")
    if score >= 0.9:
        print("  PASS (>= 0.9)")
    else:
        print("  WARN (< 0.9) — determinism threshold not met")

    print()


def cmd_rerun(args: argparse.Namespace) -> None:
    _load_env()
    config = _load_config(args.provider)
    session_id = args.session_id

    from hfabric.session.manager import SessionManager

    manager = SessionManager()
    meta = manager.get_session(session_id)
    if meta is None:
        print(f"Error: session '{session_id}' not found.", file=sys.stderr)
        sys.exit(1)

    _build_session_index(config, session_id)

    from hfabric.orchestrator.wiring import build_real_orchestrator

    print(f"Rerunning pipeline for session {session_id} from stage '{args.from_stage}'...")
    orchestrator = build_real_orchestrator(config, session_id=session_id)
    state = orchestrator.rerun(session_id, args.run_id, args.from_stage)

    manager.update_status(session_id, state.get("status", "unknown"))
    _print_results(state)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    _load_env()
    _configure_logging()
    uvicorn.run("hfabric.api.app:app", host="0.0.0.0", port=args.port, reload=False)


def cmd_serve_ui(args: argparse.Namespace) -> None:
    _load_env()
    _configure_logging()
    from streamlit.web import cli as stcli

    ui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ui", "app.py")
    if not os.path.isfile(ui_path):
        print(f"Error: UI not found at {ui_path}", file=sys.stderr)
        sys.exit(1)
    sys.argv = ["streamlit", "run", ui_path, "--server.port", str(args.port),
                "--server.headless", "true", "--server.fileWatcherType", "none"]
    stcli.main()


def cmd_serve_playground(args: argparse.Namespace) -> None:
    _load_env()
    _configure_logging()
    from streamlit.web import cli as stcli

    ui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ui", "playground.py")
    if not os.path.isfile(ui_path):
        print(f"Error: playground not found at {ui_path}", file=sys.stderr)
        sys.exit(1)
    sys.argv = ["streamlit", "run", ui_path, "--server.port", str(args.port),
                "--server.headless", "true", "--server.fileWatcherType", "none"]
    stcli.main()


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.command in ("run", "eval", "rerun", "serve", "serve-ui", "serve-playground"):
        _load_env()
        _configure_logging()
    args.func(args)


if __name__ == "__main__":
    main()
