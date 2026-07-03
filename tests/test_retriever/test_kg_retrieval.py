from __future__ import annotations

from unittest.mock import MagicMock

from hfabric.retriever.kg_retrieval import retrieve_kg_evidence
from hfabric.schemas import EvidenceChunk, KGNode


def test_retrieve_kg_evidence_finds_chunks_via_neighbours():
    kg = MagicMock()
    kg.get_entities.return_value = [
        KGNode(id="node_1", label="Material", properties={"name": "gold"}),
    ]
    kg.neighbours.return_value = [
        KGNode(
            id="node_2",
            label="Property",
            properties={"name": "recovery", "chunk_id": "chunk_001"},
        ),
    ]

    dummy_chunk = EvidenceChunk(
        chunk_id="chunk_001", doc_id="doc_1", text="test", meta={}
    )
    chunks_by_id = {"chunk_001": dummy_chunk}

    results = retrieve_kg_evidence(kg, ["gold"], chunks_by_id, hops=2)
    assert len(results) == 1
    assert results[0].chunk_id == "chunk_001"


def test_retrieve_kg_evidence_dedups():
    kg = MagicMock()
    kg.get_entities.return_value = [
        KGNode(id="node_1", label="Material", properties={}),
        KGNode(id="node_2", label="Material", properties={}),
    ]
    kg.neighbours.return_value = [
        KGNode(
            id="n_neigh",
            label="Property",
            properties={"chunk_id": "chunk_001"},
        ),
    ]

    dummy_chunk = EvidenceChunk(
        chunk_id="chunk_001", doc_id="doc_1", text="test", meta={}
    )
    chunks_by_id = {"chunk_001": dummy_chunk}

    results = retrieve_kg_evidence(kg, ["gold"], chunks_by_id, hops=2)
    assert len(results) == 1


def test_retrieve_kg_evidence_no_match_returns_empty():
    kg = MagicMock()
    kg.get_entities.return_value = []
    chunks_by_id: dict[str, EvidenceChunk] = {}

    results = retrieve_kg_evidence(kg, ["gold"], chunks_by_id, hops=2)
    assert results == []


def test_retrieve_kg_evidence_uses_provenance_key():
    kg = MagicMock()
    kg.get_entities.return_value = [
        KGNode(id="node_1", label="Material", properties={"name": "xanthate"}),
    ]
    kg.neighbours.return_value = [
        KGNode(
            id="node_2",
            label="Document",
            properties={"provenance": "chunk_002"},
        ),
    ]

    dummy_chunk = EvidenceChunk(
        chunk_id="chunk_002", doc_id="doc_1", text="test", meta={}
    )
    chunks_by_id = {"chunk_002": dummy_chunk}

    results = retrieve_kg_evidence(kg, ["xanthate"], chunks_by_id, hops=2)
    assert len(results) == 1
    assert results[0].chunk_id == "chunk_002"
