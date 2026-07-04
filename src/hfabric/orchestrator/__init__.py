from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from hfabric.config import MVPConfig
from hfabric.contracts import (
    CitationProtocol,
    ExplanationProtocol,
    ExportProtocol,
    GeneratorProtocol,
    KGProtocol,
    RetrieverProtocol,
    ScorerProtocol,
)
from hfabric.obs.traces import TraceCollector
from hfabric.orchestrator.nodes import (
    make_cite_bind_node,
    make_constraint_check_node,
    make_explain_node,
    make_export_node,
    make_generate_node,
    make_kpi_parse_node,
    make_retrieve_node,
    make_score_node,
)
from hfabric.orchestrator.state import RunState
from hfabric.storage.session_store import SessionStore


def _route_after_kpi_parse(state: RunState) -> str:
    if state.get("status") == "incomplete":
        return "export"
    return "retrieve"


def _route_after_retrieve(state: RunState) -> str:
    if state.get("status") == "incomplete":
        return "export"
    return "generate"


def _route_after_generate(state: RunState) -> str:
    if state.get("status") == "incomplete":
        return "export"
    fe2 = state.get("fe2_attempt", 0)
    if fe2 > 0 and not state.get("candidates"):
        return "generate"
    return "cite_bind"


def _route_after_cite_bind(state: RunState) -> str:
    if state.get("status") == "incomplete":
        return "export"
    fe6 = state.get("fe6_attempt", 0)
    coverage = state.get("coverage", 0.0)
    if fe6 > 0 and coverage < 0.5:
        return "generate"
    return "score"


def _route_after_constraint(state: RunState) -> str:
    if state.get("status") == "incomplete":
        return "export"
    return "explain"


def build_graph(
    llm: Any,
    retriever: RetrieverProtocol,
    generator: GeneratorProtocol,
    citation: CitationProtocol,
    scorer: ScorerProtocol,
    explanation: ExplanationProtocol,
    exporter: ExportProtocol,
    kg: KGProtocol,
    store: SessionStore,
    trace_collector: TraceCollector,
    config: MVPConfig,
):
    builder = StateGraph(RunState)

    builder.add_node(
        "kpi_parse",
        make_kpi_parse_node(llm, store, trace_collector, config),
    )
    builder.add_node(
        "retrieve",
        make_retrieve_node(retriever, store, trace_collector, config),
    )
    builder.add_node(
        "generate",
        make_generate_node(generator, store, trace_collector, config, kg=kg),
    )
    builder.add_node(
        "cite_bind",
        make_cite_bind_node(citation, store, trace_collector, config),
    )
    builder.add_node(
        "score",
        make_score_node(scorer, store, trace_collector, config),
    )
    builder.add_node(
        "constraint_check",
        make_constraint_check_node(store, trace_collector, config),
    )
    builder.add_node(
        "explain",
        make_explain_node(explanation, kg, store, trace_collector, config),
    )
    builder.add_node(
        "export",
        make_export_node(exporter, store, trace_collector, config),
    )

    builder.set_entry_point("kpi_parse")

    builder.add_conditional_edges("kpi_parse", _route_after_kpi_parse, {
        "retrieve": "retrieve",
        "export": "export",
    })

    builder.add_conditional_edges("retrieve", _route_after_retrieve, {
        "generate": "generate",
        "export": "export",
    })

    builder.add_conditional_edges("generate", _route_after_generate, {
        "cite_bind": "cite_bind",
        "generate": "generate",
        "export": "export",
    })

    builder.add_conditional_edges("cite_bind", _route_after_cite_bind, {
        "score": "score",
        "generate": "generate",
        "export": "export",
    })

    builder.add_edge("score", "constraint_check")

    builder.add_conditional_edges("constraint_check", _route_after_constraint, {
        "explain": "explain",
        "export": "export",
    })

    builder.add_edge("explain", "export")
    builder.add_edge("export", END)

    return builder.compile()


class Orchestrator:
    def __init__(
        self,
        llm: Any,
        retriever: RetrieverProtocol,
        generator: GeneratorProtocol,
        citation: CitationProtocol,
        scorer: ScorerProtocol,
        explanation: ExplanationProtocol,
        exporter: ExportProtocol,
        kg: KGProtocol,
        store: SessionStore,
        trace_collector: TraceCollector,
        config: MVPConfig,
    ):
        self._graph = build_graph(
            llm=llm,
            retriever=retriever,
            generator=generator,
            citation=citation,
            scorer=scorer,
            explanation=explanation,
            exporter=exporter,
            kg=kg,
            store=store,
            trace_collector=trace_collector,
            config=config,
        )
        self._config = config
        self._store = store

    def run(
        self, session_id: str, nl_query: str, run_id: str | None = None
    ) -> RunState:
        import uuid

        run_id = run_id or str(uuid.uuid4())[:8]
        self._store.init(run_id)

        initial_state = self._build_initial_state(session_id, run_id, nl_query)
        result = self._graph.invoke(initial_state)
        return result

    def _build_initial_state(
        self, session_id: str, run_id: str, nl_query: str
    ) -> RunState:
        return {
            "run_id": run_id,
            "session_id": session_id,
            "nl_query": nl_query,
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
        }

    def rerun(
        self,
        session_id: str,
        run_id: str,
        from_stage: str = "generate",
        edited_artifacts: dict[str, dict[str, str]] | None = None,
    ) -> RunState:
        import json
        import uuid

        new_run_id = str(uuid.uuid4())[:8]
        self._store.init(new_run_id)

        state_snapshot = self._load_run_state(run_id, from_stage)

        if edited_artifacts:
            for stage_name, artifacts in edited_artifacts.items():
                for art_name, art_value in artifacts.items():
                    self._store.save_artifact(new_run_id, stage_name, art_name, art_value)

        initial_state = self._build_initial_state(
            session_id,
            new_run_id,
            state_snapshot.get("nl_query", ""),
        )

        for field, value in state_snapshot.items():
            if field in initial_state and value is not None:
                initial_state[field] = value

        result = self._graph.invoke(initial_state)
        return result

    def _load_run_state(self, run_id: str, from_stage: str) -> dict:
        import json

        stage_order = [
            "kpi_parse", "retrieve", "generate", "cite_bind",
            "score", "constraint_check", "explain", "export",
        ]
        if from_stage not in stage_order:
            raise ValueError(f"Unknown stage: {from_stage}")

        stage_artifacts: dict[str, dict[str, str]] = {
            "kpi_parse": {"kpi_parsed": "kpi_parsed"},
            "retrieve": {"evidence": "evidence"},
            "generate": {"candidates": "candidates"},
            "cite_bind": {"cited": "cited", "coverage": "coverage"},
            "score": {"ranked": "ranked"},
            "constraint_check": {"ranked": "ranked", "fe4_dropped": "fe4_dropped"},
            "explain": {"explained": "explained"},
            "export": {"export_path": "export_path"},
        }

        state: dict = {}
        target_index = stage_order.index(from_stage)

        for stage in stage_order[:target_index]:
            for art_name, state_key in stage_artifacts.get(stage, {}).items():
                raw = self._store.load_artifact(run_id, stage, art_name)
                if raw is not None:
                    state[state_key] = json.loads(raw)

        return state