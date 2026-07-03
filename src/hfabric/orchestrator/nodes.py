from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable

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
from hfabric.schemas import (
    EvidenceChunk,
    ExplainedHypothesis,
    Hypothesis,
    KPIParsed,
    RunResult,
    ScoredHypothesis,
    TraceRecord,
)
from hfabric.storage.session_store import SessionStore

RunState = dict[str, Any]


def _serialize_hypothesis(h: Hypothesis) -> dict:
    return h.model_dump()


def _deserialize_hypothesis(d: dict) -> Hypothesis:
    return Hypothesis(**d)


def _serialize_chunk(c: EvidenceChunk) -> dict:
    return c.model_dump()


def _deserialize_chunk(d: dict) -> EvidenceChunk:
    return EvidenceChunk(**d)


def _serialize_scored(s: ScoredHypothesis) -> dict:
    return {
        "hypothesis": s.hypothesis.model_dump(),
        "score": s.score,
        "features": s.features,
        "cited_refs": {k: v.model_dump() for k, v in s.cited_refs.items()},
    }


def _deserialize_scored(d: dict) -> ScoredHypothesis:
    return ScoredHypothesis(
        hypothesis=Hypothesis(**d["hypothesis"]),
        score=d["score"],
        features=d["features"],
        cited_refs={
            k: EvidenceChunk(**v) for k, v in d.get("cited_refs", {}).items()
        },
    )


def _serialize_explained(e: ExplainedHypothesis) -> dict:
    return {
        "scored": _serialize_scored(e.scored),
        "justification": e.justification,
        "uncertainty": e.uncertainty,
        "verification_plan": e.verification_plan,
        "graph_neighbourhood": e.graph_neighbourhood,
    }


def _deserialize_explained(d: dict) -> ExplainedHypothesis:
    return ExplainedHypothesis(
        scored=_deserialize_scored(d["scored"]),
        justification=d["justification"],
        uncertainty=d["uncertainty"],
        verification_plan=d["verification_plan"],
        graph_neighbourhood=d["graph_neighbourhood"],
    )


def _make_trace(
    run_id: str,
    stage: str,
    slot: str | None = None,
    status: str = "ok",
) -> TraceRecord:
    return TraceRecord(run_id=run_id, stage=stage, slot=slot, status=status)


def _short_circuit(state: RunState) -> dict | None:
    if state.get("status") == "incomplete":
        return {}
    return None


def make_kpi_parse_node(
    llm: Any,
    store: SessionStore,
    trace_collector: TraceCollector,
    config: MVPConfig,
) -> Callable:
    def kpi_parse_node(state: RunState, runtime_config: dict | None = None) -> dict:
        if skip := _short_circuit(state):
            return skip
        run_id = state["run_id"]
        store.set_stage_state(run_id, "kpi_parse", "running")
        trace = _make_trace(run_id, "kpi_parse", slot="kpi_parse")

        t0 = time.perf_counter()
        try:
            structured = llm.with_structured_output(KPIParsed, method="json_schema")
            prompt = (
                f"Parse the following research goal into structured KPI data:\n\n"
                f"Goal: {state['nl_query']}\n\n"
                f"Extract the main metric, direction (increase/decrease), "
                f"target value, constraints, and language."
            )
            result: KPIParsed = structured.invoke(prompt)
            latency_ms = (time.perf_counter() - t0) * 1000

            kpi_dict = result.model_dump()
            kpi_dict_json = json.dumps(kpi_dict, default=str)
            trace.token_in = len(prompt)
            trace.token_out = len(kpi_dict_json)
            trace.latency_ms = latency_ms
            trace.status = "ok"

            store.save_artifact(run_id, "kpi_parse", "kpi_parsed", kpi_dict_json)
            store.set_stage_state(run_id, "kpi_parse", "done")
            trace_collector.record(
                run_id, "kpi_parse", slot="kpi_parse",
                token_in=trace.token_in, token_out=trace.token_out,
                latency_ms=latency_ms, status="ok",
            )

            return {"kpi_parsed": kpi_dict}
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            trace.status = "error"

            store.set_stage_state(run_id, "kpi_parse", "error", str(exc))
            trace_collector.record(
                run_id, "kpi_parse", slot="kpi_parse",
                token_in=0, token_out=0, latency_ms=latency_ms, status="error",
            )

            errors = state.get("errors", [])
            errors.append(f"kpi_parse failed: {exc}")
            return {"status": "incomplete", "errors": errors}

    return kpi_parse_node


def make_retrieve_node(
    retriever: RetrieverProtocol,
    store: SessionStore,
    trace_collector: TraceCollector,
    config: MVPConfig,
) -> Callable:
    def retrieve_node(state: RunState, runtime_config: dict | None = None) -> dict:
        run_id = state["run_id"]
        session_id = state["session_id"]
        store.set_stage_state(run_id, "retrieve", "running")
        trace = _make_trace(run_id, "retrieve", slot="retrieve")

        kpi_dict = state.get("kpi_parsed")
        if kpi_dict is None:
            store.set_stage_state(run_id, "retrieve", "error", "No kpi_parsed")
            errors = state.get("errors", [])
            errors.append("retrieve: no kpi_parsed in state")
            return {"status": "incomplete", "errors": errors}

        kpi = KPIParsed(**kpi_dict)
        t0 = time.perf_counter()
        try:
            result = retriever.retrieve(kpi, config, session_id)
            latency_ms = (time.perf_counter() - t0) * 1000

            evidence_list: list[EvidenceChunk] = result["evidence"]
            low_confidence: bool = result.get("low_confidence", False)

            evidence_serialized = [_serialize_chunk(c) for c in evidence_list]
            store.save_artifact(
                run_id, "retrieve", "evidence", json.dumps(evidence_serialized)
            )
            store.set_stage_state(run_id, "retrieve", "done")
            trace_collector.record(
                run_id, "retrieve", slot="retrieve",
                token_in=0, token_out=len(evidence_serialized),
                latency_ms=latency_ms, status="ok",
            )

            return {
                "evidence": evidence_serialized,
                "low_confidence": low_confidence,
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            store.set_stage_state(run_id, "retrieve", "error", str(exc))
            trace_collector.record(
                run_id, "retrieve", slot="retrieve",
                token_in=0, token_out=0, latency_ms=latency_ms, status="error",
            )
            errors = state.get("errors", [])
            errors.append(f"retrieve failed: {exc}")
            return {"evidence": [], "low_confidence": True, "errors": errors}

    return retrieve_node


def make_generate_node(
    generator: GeneratorProtocol,
    store: SessionStore,
    trace_collector: TraceCollector,
    config: MVPConfig,
) -> Callable:
    def generate_node(state: RunState, runtime_config: dict | None = None) -> dict:
        run_id = state["run_id"]
        fe2_attempt = state.get("fe2_attempt", 0)
        store.set_stage_state(run_id, "generate", "running")
        trace = _make_trace(run_id, "generate", slot="synthesizer")

        kpi_dict = state.get("kpi_parsed")
        if kpi_dict is None:
            store.set_stage_state(run_id, "generate", "error", "No kpi_parsed")
            errors = state.get("errors", [])
            errors.append("generate: no kpi_parsed")
            return {"status": "incomplete", "errors": errors}

        kpi = KPIParsed(**kpi_dict)
        evidence_raw = state.get("evidence", [])
        evidence = [_deserialize_chunk(c) for c in evidence_raw]

        if not evidence:
            store.set_stage_state(run_id, "generate", "done")
            return {"candidates": []}

        t0 = time.perf_counter()
        try:
            hypotheses: list[Hypothesis] = generator.generate(evidence, kpi, trace)
            latency_ms = (time.perf_counter() - t0) * 1000

            if not hypotheses:
                if fe2_attempt < config.fe2_max_reprompt:
                    store.set_stage_state(run_id, "generate", "running")
                    return {
                        "fe2_attempt": fe2_attempt + 1,
                        "candidates": [],
                    }
                store.set_stage_state(run_id, "generate", "incomplete", "FE2 exhausted")
                errors = state.get("errors", [])
                errors.append("generate: FE2 exhausted, no valid hypotheses")
                return {
                    "candidates": [],
                    "status": "incomplete",
                    "errors": errors,
                    "fe2_attempt": fe2_attempt + 1,
                }

            serialized = [_serialize_hypothesis(h) for h in hypotheses]
            store.save_artifact(
                run_id, "generate", "candidates", json.dumps(serialized)
            )
            store.set_stage_state(run_id, "generate", "done")
            trace_collector.record(
                run_id, "generate", slot="synthesizer",
                token_in=trace.token_in, token_out=trace.token_out,
                latency_ms=latency_ms, status=trace.status,
            )

            return {
                "candidates": serialized,
                "fe2_attempt": 0,
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            store.set_stage_state(run_id, "generate", "error", str(exc))
            trace_collector.record(
                run_id, "generate", slot="synthesizer",
                token_in=0, token_out=0, latency_ms=latency_ms, status="error",
            )
            errors = state.get("errors", [])
            errors.append(f"generate failed: {exc}")
            return {"candidates": [], "errors": errors}

    return generate_node


def make_cite_bind_node(
    citation: CitationProtocol,
    store: SessionStore,
    trace_collector: TraceCollector,
    config: MVPConfig,
) -> Callable:
    def cite_bind_node(state: RunState, runtime_config: dict | None = None) -> dict:
        run_id = state["run_id"]
        fe6_attempt = state.get("fe6_attempt", 0)
        store.set_stage_state(run_id, "cite_bind", "running")
        trace = _make_trace(run_id, "cite_bind", slot="citation")

        candidates_raw = state.get("candidates", [])
        if not candidates_raw:
            store.set_stage_state(run_id, "cite_bind", "done")
            return {"cited": [], "coverage": 0.0}

        hypotheses = [_deserialize_hypothesis(c) for c in candidates_raw]
        evidence_raw = state.get("evidence", [])
        chunks_map = {c["chunk_id"]: _deserialize_chunk(c) for c in evidence_raw}

        t0 = time.perf_counter()
        try:
            scored_list, coverage = citation.bind(hypotheses, chunks_map)
            latency_ms = (time.perf_counter() - t0) * 1000

            serialized = [_serialize_scored(s) for s in scored_list]
            store.save_artifact(run_id, "cite_bind", "cited", json.dumps(serialized))
            store.save_artifact(
                run_id, "cite_bind", "coverage", json.dumps(coverage)
            )

            if coverage < config.citation_coverage_min and fe6_attempt < config.fe6_max_cite_regenerate:
                store.set_stage_state(run_id, "cite_bind", "running")
                trace_collector.record(
                    run_id, "cite_bind", slot="citation",
                    token_in=0, token_out=len(serialized),
                    latency_ms=latency_ms, status="ok",
                )
                return {
                    "cited": serialized,
                    "coverage": coverage,
                    "fe6_attempt": fe6_attempt + 1,
                }

            store.set_stage_state(run_id, "cite_bind", "done")
            trace_collector.record(
                run_id, "cite_bind", slot="citation",
                token_in=0, token_out=len(serialized),
                latency_ms=latency_ms, status="ok",
            )

            return {
                "cited": serialized,
                "coverage": coverage,
                "fe6_attempt": 0,
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            store.set_stage_state(run_id, "cite_bind", "error", str(exc))
            trace_collector.record(
                run_id, "cite_bind", slot="citation",
                token_in=0, token_out=0, latency_ms=latency_ms, status="error",
            )
            errors = state.get("errors", [])
            errors.append(f"cite_bind failed: {exc}")
            return {"cited": [], "coverage": 0.0, "errors": errors}

    return cite_bind_node


def make_score_node(
    scorer: ScorerProtocol,
    store: SessionStore,
    trace_collector: TraceCollector,
    config: MVPConfig,
) -> Callable:
    def score_node(state: RunState, runtime_config: dict | None = None) -> dict:
        run_id = state["run_id"]
        store.set_stage_state(run_id, "score", "running")
        trace = _make_trace(run_id, "score", slot="scorer")

        cited_raw = state.get("cited", [])
        if not cited_raw:
            store.set_stage_state(run_id, "score", "done")
            return {"ranked": []}

        scored_list = [_deserialize_scored(s) for s in cited_raw]
        hypotheses = [s.hypothesis for s in scored_list]

        kpi_dict = state.get("kpi_parsed")
        if kpi_dict is None:
            store.set_stage_state(run_id, "score", "error", "No kpi_parsed")
            errors = state.get("errors", [])
            errors.append("score: no kpi_parsed")
            return {"status": "incomplete", "errors": errors}

        kpi = KPIParsed(**kpi_dict)
        evidence_raw = state.get("evidence", [])
        chunks = {c["chunk_id"]: _deserialize_chunk(c) for c in evidence_raw}

        t0 = time.perf_counter()
        try:
            ranked = scorer.score(hypotheses, chunks, kpi, scorer.kg, config)
            latency_ms = (time.perf_counter() - t0) * 1000

            merged: list[ScoredHypothesis] = []
            for r in ranked:
                for s in scored_list:
                    if s.hypothesis.claim == r.hypothesis.claim:
                        merged.append(ScoredHypothesis(
                            hypothesis=r.hypothesis,
                            score=r.score,
                            features=r.features,
                            cited_refs=s.cited_refs,
                        ))
                        break
                else:
                    merged.append(r)

            if not merged:
                merged = [ScoredHypothesis(
                    hypothesis=s.hypothesis,
                    score=s.score,
                    features=s.features,
                    cited_refs=s.cited_refs,
                ) for s in scored_list]

            serialized = [_serialize_scored(m) for m in merged]
            store.save_artifact(run_id, "score", "ranked", json.dumps(serialized))
            store.set_stage_state(run_id, "score", "done")
            trace_collector.record(
                run_id, "score", slot="scorer",
                token_in=0, token_out=len(serialized),
                latency_ms=latency_ms, status="ok",
            )

            return {"ranked": serialized}
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            store.set_stage_state(run_id, "score", "error", str(exc))
            trace_collector.record(
                run_id, "score", slot="scorer",
                token_in=0, token_out=0, latency_ms=latency_ms, status="error",
            )
            errors = state.get("errors", [])
            errors.append(f"score failed: {exc}")
            return {"ranked": [], "errors": errors}

    return score_node


def make_constraint_check_node(
    store: SessionStore,
    trace_collector: TraceCollector,
    config: MVPConfig,
) -> Callable:
    def constraint_check_node(state: RunState, runtime_config: dict | None = None) -> dict:
        run_id = state["run_id"]
        store.set_stage_state(run_id, "constraint_check", "running")
        trace = _make_trace(run_id, "constraint_check", slot="constraint")

        ranked_raw = state.get("ranked", [])
        if not ranked_raw:
            store.set_stage_state(run_id, "constraint_check", "done")
            return {"ranked": [], "fe4_dropped": []}

        kpi_dict = state.get("kpi_parsed")
        constraints: list[str] = []
        if kpi_dict:
            constraints = kpi_dict.get("constraints", [])

        from hfabric.scorer.constraint import constraint_check as _cc

        t0 = time.perf_counter()
        kept: list[dict] = []
        dropped: list[str] = []
        for item in ranked_raw:
            hyp = Hypothesis(**item["hypothesis"])
            check = _cc(hyp, constraints)
            if check["ok"]:
                kept.append(item)
            else:
                dropped.append(hyp.claim[:80])

        latency_ms = (time.perf_counter() - t0) * 1000

        store.save_artifact(run_id, "constraint_check", "ranked", json.dumps(kept))
        store.save_artifact(run_id, "constraint_check", "fe4_dropped", json.dumps(dropped))

        if not kept:
            store.set_stage_state(run_id, "constraint_check", "done")
            trace_collector.record(
                run_id, "constraint_check", slot="constraint",
                token_in=0, token_out=0, latency_ms=latency_ms, status="ok",
            )
            errors = state.get("errors", [])
            errors.append("constraint_check: all hypotheses dropped (FE4)")
            return {
                "ranked": [],
                "fe4_dropped": dropped,
                "errors": errors,
                "status": "incomplete",
            }

        store.set_stage_state(run_id, "constraint_check", "done")
        trace_collector.record(
            run_id, "constraint_check", slot="constraint",
            token_in=0, token_out=len(kept),
            latency_ms=latency_ms, status="ok",
        )

        return {"ranked": kept, "fe4_dropped": dropped}

    return constraint_check_node


def make_explain_node(
    explanation: ExplanationProtocol,
    kg: KGProtocol,
    store: SessionStore,
    trace_collector: TraceCollector,
    config: MVPConfig,
) -> Callable:
    def explain_node(state: RunState, runtime_config: dict | None = None) -> dict:
        run_id = state["run_id"]
        store.set_stage_state(run_id, "explain", "running")
        trace = _make_trace(run_id, "explain", slot="explanation")

        ranked_raw = state.get("ranked", [])
        if not ranked_raw:
            store.set_stage_state(run_id, "explain", "done")
            return {"explained": []}

        scored_list = [_deserialize_scored(s) for s in ranked_raw]
        evidence_raw = state.get("evidence", [])
        evidence = [_deserialize_chunk(c) for c in evidence_raw]

        t0 = time.perf_counter()
        try:
            explained: list[ExplainedHypothesis] = explanation.explain(
                scored_list, evidence, kg, trace
            )
            latency_ms = (time.perf_counter() - t0) * 1000

            serialized = [_serialize_explained(e) for e in explained]
            store.save_artifact(
                run_id, "explain", "explained", json.dumps(serialized)
            )
            store.set_stage_state(run_id, "explain", "done")
            trace_collector.record(
                run_id, "explain", slot="explanation",
                token_in=trace.token_in, token_out=trace.token_out,
                latency_ms=latency_ms, status=trace.status,
            )

            return {"explained": serialized}
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            store.set_stage_state(run_id, "explain", "error", str(exc))
            trace_collector.record(
                run_id, "explain", slot="explanation",
                token_in=0, token_out=0, latency_ms=latency_ms, status="error",
            )
            errors = state.get("errors", [])
            errors.append(f"explain failed: {exc}")
            return {"explained": [], "errors": errors}

    return explain_node


def make_export_node(
    exporter: ExportProtocol,
    store: SessionStore,
    trace_collector: TraceCollector,
    config: MVPConfig,
) -> Callable:
    def export_node(state: RunState, runtime_config: dict | None = None) -> dict:
        run_id = state["run_id"]
        session_id = state["session_id"]
        store.set_stage_state(run_id, "export", "running")
        trace = _make_trace(run_id, "export", slot="export")

        explained_raw = state.get("explained", [])
        kpi_dict = state.get("kpi_parsed", {})
        kpi = KPIParsed(**kpi_dict) if kpi_dict else KPIParsed(
            goal=state.get("nl_query", ""),
            kpi={"metric": "unknown", "direction": "N/A", "target": None},
            constraints=[],
            language="en",
        )

        t0 = time.perf_counter()
        try:
            result = RunResult(
                run_id=run_id,
                session_id=session_id,
                query=state.get("nl_query", ""),
                kpi=kpi,
                ranked=[_deserialize_explained(e) for e in explained_raw],
                status=state.get("status", "complete"),
            )

            export_path = exporter.export(result, session_id)
            if isinstance(export_path, tuple):
                json_path, md_path = export_path
            else:
                json_path = export_path
                md_path = ""

            latency_ms = (time.perf_counter() - t0) * 1000

            store.save_artifact(run_id, "export", "export_path", json.dumps(json_path))
            current_status = state.get("status", "running")
            final_status = "complete" if current_status == "running" else current_status
            store.set_stage_state(run_id, "export", "done")

            for stage in ["kpi_parse", "retrieve", "generate", "cite_bind",
                          "score", "constraint_check", "explain"]:
                s = store.get_stage_state(run_id, stage)
                if s and s["status"] not in ("done", "error"):
                    store.set_stage_state(run_id, stage, "done")

            trace_collector.record(
                run_id, "export", slot="export",
                token_in=0, token_out=0,
                latency_ms=latency_ms, status="ok",
            )

            return {
                "export_path": json_path,
                "export_json_path": json_path,
                "export_md_path": md_path,
                "status": final_status,
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            store.set_stage_state(run_id, "export", "error", str(exc))
            trace_collector.record(
                run_id, "export", slot="export",
                token_in=0, token_out=0, latency_ms=latency_ms, status="error",
            )
            errors = state.get("errors", [])
            errors.append(f"export failed: {exc}")
            return {"status": "incomplete", "errors": errors}

    return export_node