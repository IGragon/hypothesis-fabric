from __future__ import annotations

from unittest.mock import MagicMock

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
from hfabric.schemas import (
    EvidenceChunk,
    ExplainedHypothesis,
    Hypothesis,
    IndexArtifact,
    KGNode,
    KPIParsed,
    KPI,
    RunResult,
    ScoredHypothesis,
    TraceRecord,
)


def make_fake_llm(kpi_parsed=None):
    if kpi_parsed is None:
        kpi_parsed = KPIParsed(
            goal="increase Au flotation recovery by 5% without raising cyanide use",
            kpi=KPI(metric="Au recovery", direction="increase", target="5%"),
            constraints=["no cyanide increase"],
            language="en",
        )
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = kpi_parsed
    llm.with_structured_output.return_value = structured
    return llm


class FakeRetriever:
    def retrieve(self, kpi: KPIParsed, config: MVPConfig, session_id: str) -> dict:
        return {
            "evidence": [
                EvidenceChunk(
                    chunk_id="c1",
                    doc_id="d1",
                    text="Xanthate collectors improve gold flotation recovery by up to 10%.",
                    meta={"source": "kb"},
                ),
                EvidenceChunk(
                    chunk_id="c2",
                    doc_id="d2",
                    text="Sodium sulphide can activate oxidized gold ores in flotation.",
                    meta={"source": "session"},
                ),
            ],
            "low_confidence": False,
        }


class FakeGenerator:
    def __init__(self, responses: list[list[Hypothesis]] | None = None):
        self._responses = responses or [[]]
        self._call_count = 0
        self.last_kpi: KPIParsed | None = None
        self.last_evidence: list[EvidenceChunk] | None = None

    def generate(
        self, evidence: list[EvidenceChunk], kpi: KPIParsed, trace: TraceRecord | None = None
    ) -> list[Hypothesis]:
        self.last_evidence = evidence
        self.last_kpi = kpi
        idx = min(self._call_count, len(self._responses) - 1)
        result = self._responses[idx]
        self._call_count += 1
        if trace:
            trace.status = "ok"
            trace.token_in = 100
            trace.token_out = 200
            trace.latency_ms = 500.0
        return result


def make_valid_hypotheses() -> list[Hypothesis]:
    return [
        Hypothesis(
            claim="Xanthate collector addition increases Au recovery",
            mechanism="Xanthates chemisorb on gold surfaces increasing hydrophobicity",
            expected_effect="+5-10% Au recovery in flotation",
            evidence_refs=["c1"],
        ),
        Hypothesis(
            claim="Sodium sulphide pre-treatment activates oxidized gold",
            mechanism="Sulphidization forms a hydrophobic layer on oxidized gold particles",
            expected_effect="+3-7% Au recovery for oxidized ores",
            evidence_refs=["c2"],
        ),
    ]


def make_invalid_hypotheses() -> list[Hypothesis]:
    return [
        Hypothesis(
            claim="Bad",
            mechanism="short",
            expected_effect="",
            evidence_refs=["nonexistent"],
        ),
    ]


class FakeCitation:
    def __init__(self, coverage: float = 1.0):
        self._coverage = coverage

    def bind(
        self, hypotheses: list[Hypothesis], chunks: dict[str, EvidenceChunk]
    ) -> tuple[list[ScoredHypothesis], float]:
        scored: list[ScoredHypothesis] = []
        for h in hypotheses:
            cited: dict[str, EvidenceChunk] = {}
            for ref in h.evidence_refs:
                if ref in chunks:
                    cited[ref] = chunks[ref]
            scored.append(ScoredHypothesis(
                hypothesis=h, score=0.0, features={}, cited_refs=cited,
            ))
        return (scored, self._coverage)


class FakeKG:
    def add_entities(self, entities, session_id=None, source=""):
        pass

    def add_edges(self, edges, session_id=None, source=""):
        pass

    def traverse(self, cypher, params=None):
        return []

    def get_entities(self, name):
        return []

    def neighbours(self, node_id, hops=2):
        return []

    def conflicts(self, source_id):
        return []

    def dump(self, path):
        pass

    def load(self, path):
        pass


class FakeScorer:
    def __init__(self):
        self.kg = FakeKG()

    def score(
        self, hypotheses, chunks, kpi, kg, config
    ) -> list[ScoredHypothesis]:
        results: list[ScoredHypothesis] = []
        for i, h in enumerate(hypotheses):
            results.append(ScoredHypothesis(
                hypothesis=h,
                score=0.9 - i * 0.1,
                features={"novelty": 0.5, "feasibility": 0.8, "effect": 0.7},
                cited_refs={
                    ref: EvidenceChunk(
                        chunk_id=ref, doc_id="d0", text="dummy", meta={}
                    )
                    for ref in h.evidence_refs
                },
            ))
        return results


class FakeExplainer:
    def explain(
        self, ranked, evidence, kg, trace=None
    ) -> list[ExplainedHypothesis]:
        results: list[ExplainedHypothesis] = []
        for s in ranked:
            results.append(ExplainedHypothesis(
                scored=s,
                justification="Plausible based on evidence.",
                uncertainty="Unknown.",
                verification_plan="Run flotation test.",
                graph_neighbourhood=["Material: gold"],
            ))
        if trace:
            trace.token_in = 300
            trace.token_out = 500
            trace.latency_ms = 1000.0
            trace.status = "ok"
        return results


class FakeExporter:
    def export(self, result: RunResult, session_id: str) -> tuple[str, str]:
        return (f"sessions/{session_id}/export/hypotheses.json",
                f"sessions/{session_id}/export/report.md")


class FakeTraceCollector:
    def __init__(self):
        self.records: list[TraceRecord] = []

    def record(self, run_id, stage, slot=None, token_in=0, token_out=0,
               latency_ms=0.0, status="ok"):
        t = TraceRecord(
            run_id=run_id, stage=stage, slot=slot,
            token_in=token_in, token_out=token_out,
            latency_ms=latency_ms, status=status,
        )
        self.records.append(t)
        return t

    def wrap_llm_call(self, run_id, stage, slot, llm_fn, *args, **kwargs):
        return llm_fn(*args, **kwargs)
