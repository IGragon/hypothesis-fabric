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
    ranked = state.get("ranked", [])
    if not ranked:
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
        make_generate_node(generator, store, trace_collector, config),
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

    def run(self, session_id: str, nl_query: str) -> RunState:
        import uuid

        run_id = str(uuid.uuid4())[:8]
        self._store.init(run_id)

        initial_state: RunState = {
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

        result = self._graph.invoke(initial_state)
        return result