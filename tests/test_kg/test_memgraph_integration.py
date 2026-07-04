from __future__ import annotations

import json
import os
import tempfile

import pytest
from neo4j import GraphDatabase

from hfabric.kg.client import MemgraphKG

MEMGRAPH_URI = "bolt://localhost:7687"


def _memgraph_reachable() -> bool:
    try:
        driver = GraphDatabase.driver(MEMGRAPH_URI)
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


skip_if_no_memgraph = pytest.mark.skipif(
    not _memgraph_reachable(),
    reason="Memgraph not running at bolt://localhost:7687",
)


def _clean_graph(uri: str) -> None:
    driver = GraphDatabase.driver(uri)
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
    driver.close()


@pytest.fixture
def fresh_memgraph():
    _clean_graph(MEMGRAPH_URI)
    kg = MemgraphKG(MEMGRAPH_URI)
    yield kg
    _clean_graph(MEMGRAPH_URI)


class TestMemgraphIntegration:
    @skip_if_no_memgraph
    def test_add_and_get_entities(self, fresh_memgraph):
        entities = [
            {"label": "Material", "properties": {"name": "gold", "category": "element"}},
            {"label": "Material", "properties": {"name": "silver", "category": "element"}},
            {"label": "Property", "properties": {"name": "recovery of gold", "category": "recovery", "value": "92.5%"}},
        ]
        fresh_memgraph.add_entities(entities, session_id="test_run", source="kb")
        result = fresh_memgraph.get_entities("gold")
        assert len(result) >= 1
        assert result[0].properties["name"] == "gold"

    @skip_if_no_memgraph
    def test_add_edges_and_neighbours(self, fresh_memgraph):
        entities = [
            {"label": "Material", "properties": {"name": "gold", "category": "element"}},
            {"label": "Property", "properties": {"name": "Au recovery", "category": "recovery", "value": "92.5%"}},
        ]
        fresh_memgraph.add_entities(entities, session_id="test_run", source="kb")

        gold_nodes = fresh_memgraph.get_entities("gold")
        assert len(gold_nodes) > 0
        gold_id = gold_nodes[0].id

        edges = [
            {
                "from_label": "Material", "from_name": "gold",
                "to_label": "Property", "to_name": "Au recovery",
                "rel_type": "influences",
                "provenance": {"chunk_id": "c1", "doc_id": "d1"},
            }
        ]
        fresh_memgraph.add_edges(edges, session_id="test_run", source="kb")

        neighbours = fresh_memgraph.neighbours(gold_id, hops=1)
        assert len(neighbours) >= 1

    @skip_if_no_memgraph
    def test_neighbours_hops_2_and_3(self, fresh_memgraph):
        entities = [
            {"label": "Material", "properties": {"name": "gold", "category": "element"}},
            {"label": "Process", "properties": {"name": "flotation", "category": "flotation"}},
            {"label": "Property", "properties": {"name": "Au recovery", "category": "recovery", "value": "92.5%"}},
        ]
        fresh_memgraph.add_entities(entities, session_id="test_run", source="kb")

        gold_id = fresh_memgraph.get_entities("gold")[0].id

        edges = [
            {"from_label": "Material", "from_name": "gold", "to_label": "Process", "to_name": "flotation", "rel_type": "influences", "provenance": {"chunk_id": "c1"}},
            {"from_label": "Process", "from_name": "flotation", "to_label": "Property", "to_name": "Au recovery", "rel_type": "influences", "provenance": {"chunk_id": "c2"}},
        ]
        fresh_memgraph.add_edges(edges, session_id="test_run", source="kb")

        n1 = fresh_memgraph.neighbours(gold_id, hops=1)
        n2 = fresh_memgraph.neighbours(gold_id, hops=2)
        assert len(n2) > 0

        n3 = fresh_memgraph.neighbours(gold_id, hops=3)
        assert len(n3) > 0

    @skip_if_no_memgraph
    def test_session_scoping(self, fresh_memgraph):
        fresh_memgraph.add_entities(
            [{"label": "Material", "properties": {"name": "gold", "category": "element"}}],
            session_id="session_A", source="session",
        )
        fresh_memgraph.add_entities(
            [{"label": "Material", "properties": {"name": "silver", "category": "element"}}],
            session_id="session_B", source="session",
        )
        gold_a = fresh_memgraph.get_entities("gold")
        silver_b = fresh_memgraph.get_entities("silver")
        assert len(gold_a) >= 1
        assert len(silver_b) >= 1

    @skip_if_no_memgraph
    def test_dump_load_roundtrip(self, fresh_memgraph):
        entities = [
            {"label": "Material", "properties": {"name": "copper", "category": "element"}},
            {"label": "Material", "properties": {"name": "pyrite", "category": "mineral"}},
        ]
        fresh_memgraph.add_entities(entities, session_id="test_run", source="kb")

        coppers = fresh_memgraph.get_entities("copper")
        assert len(coppers) > 0

        dump_path = os.path.join(tempfile.gettempdir(), "test_memgraph_dump.json")
        fresh_memgraph.dump(dump_path)

        assert os.path.exists(dump_path)
        with open(dump_path) as f:
            data = json.load(f)
        assert len(data["nodes"]) > 0

        os.remove(dump_path)
