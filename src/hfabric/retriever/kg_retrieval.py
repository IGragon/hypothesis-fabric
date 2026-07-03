from __future__ import annotations

from hfabric.contracts import KGProtocol
from hfabric.schemas import EvidenceChunk


def retrieve_kg_evidence(
    kg: KGProtocol,
    entities: list[str],
    chunks_by_id: dict[str, EvidenceChunk],
    hops: int = 2,
) -> list[EvidenceChunk]:
    seen_chunk_ids: set[str] = set()
    results: list[EvidenceChunk] = []

    for entity_name in entities:
        nodes = kg.get_entities(entity_name)
        for node in nodes:
            neighbours = kg.neighbours(node.id, hops)
            for neighbour in neighbours:
                for key in ("chunk_id", "provenance", "source_chunk"):
                    chunk_id = neighbour.properties.get(key)
                    if chunk_id and chunk_id in chunks_by_id:
                        if chunk_id not in seen_chunk_ids:
                            seen_chunk_ids.add(chunk_id)
                            results.append(chunks_by_id[chunk_id])
                        break

            for key in ("chunk_id", "provenance", "source_chunk"):
                chunk_id = node.properties.get(key)
                if chunk_id and chunk_id in chunks_by_id:
                    if chunk_id not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk_id)
                        results.append(chunks_by_id[chunk_id])
                    break

    return results
