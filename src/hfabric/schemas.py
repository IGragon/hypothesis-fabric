from __future__ import annotations

from pydantic import BaseModel


class KPI(BaseModel):
    metric: str
    direction: str
    target: str | None = None


class KPIParsed(BaseModel):
    goal: str
    kpi: KPI
    constraints: list[str]
    language: str


class EvidenceChunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    meta: dict


class Hypothesis(BaseModel):
    claim: str
    mechanism: str
    expected_effect: str
    evidence_refs: list[str]


class ScoredHypothesis(BaseModel):
    hypothesis: Hypothesis
    score: float
    features: dict[str, float]
    cited_refs: dict[str, EvidenceChunk]


class ExplainedHypothesis(BaseModel):
    scored: ScoredHypothesis
    justification: str
    uncertainty: str
    verification_plan: str
    graph_neighbourhood: list[str]


class RunResult(BaseModel):
    run_id: str
    session_id: str
    query: str
    kpi: KPIParsed
    ranked: list[ExplainedHypothesis]
    export_path: str | None = None
    status: str = "incomplete"


class TraceRecord(BaseModel):
    run_id: str
    stage: str
    slot: str | None = None
    token_in: int = 0
    token_out: int = 0
    latency_ms: float = 0.0
    status: str = "ok"


class IndexArtifact(BaseModel):
    index_dir: str
    faiss_path: str
    chunks_path: str
    num_chunks: int
    source: str
    session_id: str | None = None


class KGNode(BaseModel):
    id: str
    label: str
    properties: dict
