from __future__ import annotations

import json

import pytest

from hfabric.kg.schema import EDGE_TYPES, NODE_LABELS
from hfabric.schemas import KGNode


class FakeMemgraphKG:
    def __init__(self):
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"4:{self._counter}:0"

    def add_entities(
        self,
        entities: list[dict],
        session_id: str | None = None,
        source: str = "",
    ) -> None:
        for entity in entities:
            label = entity["label"]
            if label not in NODE_LABELS:
                raise ValueError(f"Invalid node label: {label}")
            props = dict(entity["properties"])
            props["session_id"] = session_id
            props["source"] = source
            node_id = self._next_id()
            self._nodes[node_id] = {
                "id": node_id,
                "label": label,
                "properties": props,
            }

    def add_edges(
        self,
        edges: list[dict],
        session_id: str | None = None,
        source: str = "",
    ) -> None:
        for edge in edges:
            from_label = edge["from_label"]
            to_label = edge["to_label"]
            rel_type = edge["rel_type"]
            if from_label not in NODE_LABELS:
                raise ValueError(f"Invalid from_label: {from_label}")
            if to_label not in NODE_LABELS:
                raise ValueError(f"Invalid to_label: {to_label}")
            if rel_type not in EDGE_TYPES:
                raise ValueError(f"Invalid rel_type: {rel_type}")

            from_name = edge["from_name"]
            to_name = edge["to_name"]

            from_nodes = [
                n
                for n in self._nodes.values()
                if n["label"] == from_label
                and n["properties"].get("name") == from_name
                and n["properties"].get("session_id") == session_id
                and n["properties"].get("source") == source
            ]
            to_nodes = [
                n
                for n in self._nodes.values()
                if n["label"] == to_label
                and n["properties"].get("name") == to_name
                and n["properties"].get("session_id") == session_id
                and n["properties"].get("source") == source
            ]

            if from_nodes and to_nodes:
                provenance = edge.get("provenance", {})
                self._edges.append(
                    {
                        "from_id": from_nodes[0]["id"],
                        "to_id": to_nodes[0]["id"],
                        "rel_type": rel_type,
                        "properties": {
                            **provenance,
                            "session_id": session_id,
                            "source": source,
                        },
                    }
                )

    def traverse(self, cypher: str, params: dict | None = None) -> list[KGNode]:
        return []

    def get_entities(self, name: str) -> list[KGNode]:
        results: list[KGNode] = []
        for node in self._nodes.values():
            node_name = node["properties"].get("name", "")
            if name.lower() in node_name.lower():
                results.append(
                    KGNode(
                        id=node["id"],
                        label=node["label"],
                        properties=node["properties"],
                    )
                )
        return results

    def neighbours(self, node_id: str, hops: int = 2) -> list[KGNode]:
        visited: set[str] = {node_id}
        frontier: set[str] = {node_id}

        for _ in range(hops):
            next_frontier: set[str] = set()
            for nid in frontier:
                for edge in self._edges:
                    if edge["from_id"] == nid and edge["to_id"] not in visited:
                        next_frontier.add(edge["to_id"])
                        visited.add(edge["to_id"])
                    if edge["to_id"] == nid and edge["from_id"] not in visited:
                        next_frontier.add(edge["from_id"])
                        visited.add(edge["from_id"])
            frontier = next_frontier

        results: list[KGNode] = []
        for nid in visited:
            if nid != node_id and nid in self._nodes:
                node = self._nodes[nid]
                results.append(
                    KGNode(
                        id=node["id"],
                        label=node["label"],
                        properties=node["properties"],
                    )
                )
        return results

    def conflicts(self, source_id: str) -> list[KGNode]:
        results: list[KGNode] = []
        for edge in self._edges:
            if edge["rel_type"] == "contradicts":
                if edge["from_id"] == source_id and edge["to_id"] in self._nodes:
                    node = self._nodes[edge["to_id"]]
                    results.append(
                        KGNode(
                            id=node["id"],
                            label=node["label"],
                            properties=node["properties"],
                        )
                    )
                if edge["to_id"] == source_id and edge["from_id"] in self._nodes:
                    node = self._nodes[edge["from_id"]]
                    results.append(
                        KGNode(
                            id=node["id"],
                            label=node["label"],
                            properties=node["properties"],
                        )
                    )
        return results

    def dump(self, path: str) -> None:
        data = {
            "nodes": [
                {
                    "id": n["id"],
                    "labels": [n["label"]],
                    "properties": n["properties"],
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "id": f"e_{i}",
                    "from_id": e["from_id"],
                    "to_id": e["to_id"],
                    "rel_type": e["rel_type"],
                    "properties": e["properties"],
                }
                for i, e in enumerate(self._edges)
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        with open(path) as f:
            data = json.load(f)

        self._nodes = {}
        self._edges = []

        id_map: dict[str, str] = {}
        for node_data in data["nodes"]:
            old_id = node_data["id"]
            labels = node_data["labels"]
            props = node_data["properties"]
            label = labels[0] if labels else ""
            new_id = self._next_id()
            id_map[old_id] = new_id
            self._nodes[new_id] = {
                "id": new_id,
                "label": label,
                "properties": props,
            }

        for i, edge_data in enumerate(data["edges"]):
            from_id = id_map.get(edge_data["from_id"])
            to_id = id_map.get(edge_data["to_id"])
            if from_id and to_id:
                self._edges.append(
                    {
                        "from_id": from_id,
                        "to_id": to_id,
                        "rel_type": edge_data["rel_type"],
                        "properties": edge_data["properties"],
                    }
                )


@pytest.fixture
def fake_kg() -> FakeMemgraphKG:
    return FakeMemgraphKG()
