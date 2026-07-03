from __future__ import annotations

from hfabric.config import MVPConfig
from hfabric.schemas import EvidenceChunk, Hypothesis, KPIParsed, TraceRecord

from .synth import CandidateSynthesizer


def generate(
    evidence: list[EvidenceChunk],
    kpi: KPIParsed,
    trace: TraceRecord | None = None,
) -> list[Hypothesis]:
    from hfabric.llm import create_chat_model

    config = MVPConfig()
    llm = create_chat_model(config.provider, config.model)
    synth = CandidateSynthesizer(llm, config)
    return synth.generate(evidence, kpi, trace)


__all__ = ["CandidateSynthesizer", "generate"]
