from __future__ import annotations

import json

from neo4j import GraphDatabase

from hfabric.kg.schema import DEFAULT_EDGE_TYPES, DEFAULT_NODE_LABELS
from hfabric.schemas import KGNode


class MemgraphKG:
    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        node_labels: set[str] | None = None,
        edge_types: set[str] | None = None,
    ):
        self._driver = GraphDatabase.driver(
            uri,
            connection_timeout=5,
            max_connection_lifetime=60,
        )
        self._driver.verify_connectivity()
        self._node_labels = set(node_labels) if node_labels is not None else set(DEFAULT_NODE_LABELS)
        self._edge_types = set(edge_types) if edge_types is not None else set(DEFAULT_EDGE_TYPES)
        try:
            self._create_indices()
        except Exception:
            pass

    @property
    def node_labels(self) -> set[str]:
        return set(self._node_labels)

    @property
    def edge_types(self) -> set[str]:
        return set(self._edge_types)

    def _create_indices(self) -> None:
        index_queries: list[str] = []
        for label in sorted(self._node_labels):
            index_queries.extend(
                [
                    f"CREATE INDEX ON :{label}(name)",
                    f"CREATE INDEX ON :{label}(session_id)",
                    f"CREATE INDEX ON :{label}(source)",
                ]
            )
        with self._driver.session() as session:
            for query in index_queries:
                try:
                    session.run(query)
                except Exception:
                    pass

    def add_entities(
        self,
        entities: list[dict],
        session_id: str | None = None,
        source: str = "",
    ) -> None:
        try:
            groups: dict[str, list[dict]] = {}
            for entity in entities:
                label = entity["label"]
                if label not in self._node_labels:
                    continue
                props = dict(entity["properties"])
                props["name"] = props.get("name", "")
                groups.setdefault(label, []).append(props)

            with self._driver.session() as session:
                for label, batch in groups.items():
                    for i in range(0, len(batch), 500):
                        chunk = batch[i : i + 500]
                        cypher = (
                            f"UNWIND $rows AS row "
                            f"MERGE (n:{label} {{name: row.name, session_id: $session_id, source: $source}}) "
                            "SET n += row"
                        )
                        try:
                            session.run(cypher, rows=chunk, session_id=session_id, source=source)
                        except Exception:
                            pass
        except Exception:
            pass

    def add_edges(
        self,
        edges: list[dict],
        session_id: str | None = None,
        source: str = "",
    ) -> None:
        groups: dict[tuple[str, str, str], list[dict]] = {}
        for edge in edges:
            from_label = edge["from_label"]
            to_label = edge["to_label"]
            rel_type = edge["rel_type"]
            if from_label not in self._node_labels:
                continue
            if to_label not in self._node_labels:
                continue
            if rel_type not in self._edge_types:
                continue
            key = (from_label, to_label, rel_type)
            groups.setdefault(key, []).append({
                "from_name": edge["from_name"],
                "to_name": edge["to_name"],
                "provenance": edge.get("provenance", {}),
            })

        try:
            with self._driver.session() as session:
                for (from_label, to_label, rel_type), batch in groups.items():
                    for i in range(0, len(batch), 500):
                        chunk = batch[i : i + 500]
                        cypher = (
                            f"UNWIND $rows AS row "
                            f"MATCH (from:{from_label} {{name: row.from_name, session_id: $session_id, source: $source}}) "
                            f"MATCH (to:{to_label} {{name: row.to_name, session_id: $session_id, source: $source}}) "
                            f"MERGE (from)-[r:{rel_type}]->(to) "
                            "SET r.session_id = $session_id, r.source = $source, r += row.provenance"
                        )
                        try:
                            session.run(cypher, rows=chunk, session_id=session_id, source=source)
                        except Exception:
                            pass
        except Exception:
            pass

    def traverse(self, cypher: str, params: dict | None = None) -> list[KGNode]:
        """Traverse is designed to be used internally on pre-serialised data and not called directly by the user."""
        if params is None:
            params = {}
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            nodes: list[KGNode] = []
            for record in result:
                for value in record.values():
                    if hasattr(value, "element_id") and hasattr(value, "labels"):
                        node_labels = list(value.labels)
                        nodes.append(
                            KGNode(
                                id=value.element_id,
                                label=node_labels[0] if node_labels else "",
                                properties=dict(value),
                            )
                        )
            return nodes

    def get_entities(self, name: str) -> list[KGNode]:
        labels_list = sorted(self._node_labels)
        cypher = (
            "UNWIND $labels AS lbl "
            "MATCH (n) "
            "WHERE n.name CONTAINS $name AND lbl IN labels(n) "
            "RETURN DISTINCT n"
        )
        with self._driver.session() as session:
            result = session.run(cypher, name=name, labels=labels_list)
            nodes: list[KGNode] = []
            for record in result:
                node = record["n"]
                node_labels = list(node.labels)
                nodes.append(
                    KGNode(
                        id=node.element_id,
                        label=node_labels[0] if node_labels else "",
                        properties=dict(node),
                    )
                )
            return nodes

    def neighbours(self, node_id: str, hops: int = 2) -> list[KGNode]:
        hops_int = int(hops)
        if hops_int < 1:
            return []
        cypher = (
            f"MATCH (n)-[*1..{hops_int}]-(m) "
            "WHERE elementId(n) = $node_id "
            "RETURN DISTINCT m"
        )
        with self._driver.session() as session:
            result = session.run(cypher, node_id=node_id)
            nodes: list[KGNode] = []
            for record in result:
                node = record["m"]
                node_labels = list(node.labels)
                nodes.append(
                    KGNode(
                        id=node.element_id,
                        label=node_labels[0] if node_labels else "",
                        properties=dict(node),
                    )
                )
            return nodes

    def conflicts(self, source_id: str) -> list[KGNode]:
        cypher = (
            "MATCH (s1:Source {id: $source_id})-[r:contradicts]-(s2) "
            "RETURN DISTINCT s2"
        )
        with self._driver.session() as session:
            result = session.run(cypher, source_id=source_id)
            nodes: list[KGNode] = []
            for record in result:
                node = record["s2"]
                node_labels = list(node.labels)
                nodes.append(
                    KGNode(
                        id=node.element_id,
                        label=node_labels[0] if node_labels else "",
                        properties=dict(node),
                    )
                )
            return nodes

    def dump(self, path: str) -> None:
        with self._driver.session() as session:
            nodes_result = session.run(
                "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties"
            )
            nodes = [
                {
                    "id": record["id"],
                    "labels": list(record["labels"]),
                    "properties": dict(record["properties"]),
                }
                for record in nodes_result
            ]

            edges_result = session.run(
                "MATCH (a)-[r]->(b) "
                "RETURN elementId(r) AS id, elementId(a) AS from_id, "
                "elementId(b) AS to_id, type(r) AS rel_type, properties(r) AS properties"
            )
            edges = [
                {
                    "id": record["id"],
                    "from_id": record["from_id"],
                    "to_id": record["to_id"],
                    "rel_type": record["rel_type"],
                    "properties": dict(record["properties"]),
                }
                for record in edges_result
            ]

        with open(path, "w") as f:
            json.dump({"nodes": nodes, "edges": edges}, f, indent=2)

    def load(self, path: str) -> None:
        with open(path) as f:
            data = json.load(f)

        with self._driver.session() as session:
            for node_data in data["nodes"]:
                labels = node_data["labels"]
                props = node_data["properties"]
                name = props.get("name", "")
                session_id = props.get("session_id")
                source = props.get("source", "")
                old_id = node_data["id"]

                valid_labels = [l for l in labels if l in self._node_labels]
                if not valid_labels:
                    continue
                label = valid_labels[0]

                cypher = (
                    f"MERGE (n:{label} {{name: $name, session_id: $session_id, source: $source}}) "
                    "SET n += $properties "
                    "SET n._import_id = $_import_id"
                )
                session.run(
                    cypher,
                    name=name,
                    session_id=session_id,
                    source=source,
                    properties=props,
                    _import_id=old_id,
                )

            for edge_data in data["edges"]:
                rel_type = edge_data["rel_type"]
                if rel_type not in self._edge_types:
                    continue
                cypher = (
                    f"MATCH (a {{_import_id: $_from_id}}), (b {{_import_id: $_to_id}}) "
                    f"MERGE (a)-[r:{rel_type}]->(b) "
                    "SET r += $properties"
                )
                session.run(
                    cypher,
                    _from_id=edge_data["from_id"],
                    _to_id=edge_data["to_id"],
                    properties=edge_data["properties"],
                )

            session.run("MATCH (n) WHERE n._import_id IS NOT NULL REMOVE n._import_id")
