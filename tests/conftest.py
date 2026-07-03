from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from hfabric.config import MVPConfig
from hfabric.schemas import (
    EvidenceChunk,
    ExplainedHypothesis,
    Hypothesis,
    KPI,
    KPIParsed,
    KGNode,
    ScoredHypothesis,
)


@pytest.fixture
def mvp_config() -> MVPConfig:
    return MVPConfig()


@pytest.fixture
def sample_kpi() -> KPIParsed:
    return KPIParsed(
        goal="increase Au flotation recovery by 5% without raising cyanide use",
        kpi=KPI(metric="Au recovery", direction="increase", target="5%"),
        constraints=["no cyanide increase"],
        language="en",
    )


@pytest.fixture
def sample_chunks() -> list[EvidenceChunk]:
    return [
        EvidenceChunk(
            chunk_id="chunk_001",
            doc_id="doc_1",
            text="Xanthate collectors improve gold flotation recovery by up to 10%.",
            meta={"source": "kb", "page": 1},
        ),
        EvidenceChunk(
            chunk_id="chunk_002",
            doc_id="doc_1",
            text="Cyanide is commonly used as a depressant in flotation circuits.",
            meta={"source": "kb", "page": 2},
        ),
        EvidenceChunk(
            chunk_id="chunk_003",
            doc_id="doc_2",
            text="Sodium sulphide can activate oxidized gold ores in flotation.",
            meta={"source": "session", "page": 5},
        ),
    ]


@pytest.fixture
def sample_hypotheses() -> list[Hypothesis]:
    return [
        Hypothesis(
            claim="Xanthate collector addition increases Au recovery",
            mechanism="Xanthates chemisorb on gold surfaces increasing hydrophobicity",
            expected_effect="+5-10% Au recovery",
            evidence_refs=["chunk_001"],
        ),
        Hypothesis(
            claim="Sodium sulphide pre-treatment activates oxidized gold",
            mechanism="Sulphidization forms a hydrophobic layer on oxidized gold particles",
            expected_effect="+3-7% Au recovery for oxidized ores",
            evidence_refs=["chunk_003"],
        ),
    ]


@pytest.fixture
def sample_scored() -> list[ScoredHypothesis]:
    return [
        ScoredHypothesis(
            hypothesis=h,
            score=0.75,
            features={"novelty": 0.5, "feasibility": 0.8, "effect": 0.9},
            cited_refs={
                ref: EvidenceChunk(chunk_id=ref, doc_id="doc_1", text="dummy", meta={})
                for ref in h.evidence_refs
            },
        )
        for h in [
            Hypothesis(
                claim="Xanthate collector addition increases Au recovery",
                mechanism="Xanthates chemisorb on gold surfaces increasing hydrophobicity",
                expected_effect="+5-10% Au recovery",
                evidence_refs=["chunk_001"],
            ),
        ]
    ]


@pytest.fixture
def fake_kg() -> MagicMock:
    kg = MagicMock()
    kg.get_entities.return_value = [
        KGNode(id="node_1", label="Material", properties={"name": "gold"}),
    ]
    kg.neighbours.return_value = [
        KGNode(id="node_2", label="Property", properties={"name": "Au recovery", "value": "high"}),
    ]
    kg.traverse.return_value = []
    return kg
