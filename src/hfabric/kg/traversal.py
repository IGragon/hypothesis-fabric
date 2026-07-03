from __future__ import annotations

from hfabric.kg.client import MemgraphKG
from hfabric.schemas import KGNode


def bfs_traverse(client: MemgraphKG, start_id: str, hops: int = 2) -> list[KGNode]:
    return client.neighbours(start_id, hops)
