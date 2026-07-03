from __future__ import annotations

import json
import os
import tempfile

import pytest

from hfabric.schemas import KGNode
from tests.test_kg.conftest import FakeMemgraphKG


class TestAddEntities:
    def test_creates_node_with_label_and_properties(self, fake_kg):
        fake_kg.add_entities(
            [{"label": "Material", "properties": {"name": "gold", "density": 19.3}}],
            session_id="s1",
            source="kb",
        )

        assert len(fake_kg._nodes) == 1
        node = list(fake_kg._nodes.values())[0]
        assert node["label"] == "Material"
        assert node["properties"]["name"] == "gold"
        assert node["properties"]["density"] == 19.3
        assert node["properties"]["session_id"] == "s1"
        assert node["properties"]["source"] == "kb"

    def test_session_id_and_source_added_to_properties(self, fake_kg):
        fake_kg.add_entities(
            [{"label": "Property", "properties": {"name": "Au recovery", "value": "95%"}}],
            session_id="session-abc",
            source="document_1",
        )

        node = list(fake_kg._nodes.values())[0]
        assert node["properties"]["session_id"] == "session-abc"
        assert node["properties"]["source"] == "document_1"

    def test_multiple_entities(self, fake_kg):
        entities = [
            {"label": "Material", "properties": {"name": "gold"}},
            {"label": "Material", "properties": {"name": "silver"}},
            {"label": "Property", "properties": {"name": "Au recovery"}},
        ]

        fake_kg.add_entities(entities, session_id="s1", source="kb")

        assert len(fake_kg._nodes) == 3
        labels = {n["label"] for n in fake_kg._nodes.values()}
        assert labels == {"Material", "Property"}

    def test_rejects_invalid_label(self, fake_kg):
        with pytest.raises(ValueError, match="Invalid node label"):
            fake_kg.add_entities(
                [{"label": "InvalidLabel", "properties": {"name": "test"}}],
            )

    def test_no_string_interpolation_in_node_queries(self, fake_kg):
        fake_kg.add_entities(
            [{"label": "Material", "properties": {"name": "O'Reilly & Sons"}}],
            session_id="s1",
            source="kb",
        )

        node = list(fake_kg._nodes.values())[0]
        assert node["properties"]["name"] == "O'Reilly & Sons"

    def test_entities_without_session_id(self, fake_kg):
        fake_kg.add_entities(
            [{"label": "Process", "properties": {"name": "flotation"}}],
        )

        node = list(fake_kg._nodes.values())[0]
        assert node["properties"]["session_id"] is None
        assert node["properties"]["source"] == ""


class TestAddEdges:
    def test_creates_edge_between_nodes(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Property", "properties": {"name": "Au recovery"}},
            ],
            session_id="s1",
            source="kb",
        )

        fake_kg.add_edges(
            [
                {
                    "from_label": "Material",
                    "from_name": "gold",
                    "to_label": "Property",
                    "to_name": "Au recovery",
                    "rel_type": "influences",
                    "provenance": {"chunk_id": "c1"},
                }
            ],
            session_id="s1",
            source="kb",
        )

        assert len(fake_kg._edges) == 1
        edge = fake_kg._edges[0]
        assert edge["rel_type"] == "influences"
        assert edge["properties"]["chunk_id"] == "c1"
        assert edge["properties"]["session_id"] == "s1"
        assert edge["properties"]["source"] == "kb"

    def test_edge_includes_provenance_session_source(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Process", "properties": {"name": "flotation"}},
                {"label": "Parameter", "properties": {"name": "pH"}},
            ],
            session_id="session-x",
            source="paper_1",
        )

        fake_kg.add_edges(
            [
                {
                    "from_label": "Process",
                    "from_name": "flotation",
                    "to_label": "Parameter",
                    "to_name": "pH",
                    "rel_type": "measured_as",
                    "provenance": {"chunk_id": "c2", "confidence": 0.9},
                }
            ],
            session_id="session-x",
            source="paper_1",
        )

        edge = fake_kg._edges[0]
        assert edge["properties"]["chunk_id"] == "c2"
        assert edge["properties"]["confidence"] == 0.9
        assert edge["properties"]["session_id"] == "session-x"
        assert edge["properties"]["source"] == "paper_1"

    def test_edge_not_created_if_nodes_missing(self, fake_kg):
        fake_kg.add_entities(
            [{"label": "Material", "properties": {"name": "gold"}}],
            session_id="s1",
        )

        fake_kg.add_edges(
            [
                {
                    "from_label": "Material",
                    "from_name": "gold",
                    "to_label": "Property",
                    "to_name": "nonexistent",
                    "rel_type": "influences",
                    "provenance": {},
                }
            ],
            session_id="s1",
        )

        assert len(fake_kg._edges) == 0

    def test_rejects_invalid_edge_type(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Property", "properties": {"name": "Au recovery"}},
            ],
        )

        with pytest.raises(ValueError, match="Invalid rel_type"):
            fake_kg.add_edges(
                [
                    {
                        "from_label": "Material",
                        "from_name": "gold",
                        "to_label": "Property",
                        "to_name": "Au recovery",
                        "rel_type": "invalid_type",
                        "provenance": {},
                    }
                ],
            )

    def test_rejects_invalid_from_label(self, fake_kg):
        with pytest.raises(ValueError, match="Invalid from_label"):
            fake_kg.add_edges(
                [
                    {
                        "from_label": "FakeLabel",
                        "from_name": "gold",
                        "to_label": "Property",
                        "to_name": "Au recovery",
                        "rel_type": "influences",
                        "provenance": {},
                    }
                ],
            )


class TestGetEntities:
    def test_exact_match(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Material", "properties": {"name": "silver"}},
            ],
        )

        results = fake_kg.get_entities("gold")
        assert len(results) == 1
        assert results[0].label == "Material"
        assert results[0].properties["name"] == "gold"

    def test_partial_match(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Property", "properties": {"name": "Au recovery"}},
                {"label": "Property", "properties": {"name": "Ag recovery"}},
            ],
        )

        results = fake_kg.get_entities("recovery")
        assert len(results) == 2

    def test_case_insensitive_match(self, fake_kg):
        fake_kg.add_entities(
            [{"label": "Material", "properties": {"name": "GOLD"}}],
        )

        results = fake_kg.get_entities("gold")
        assert len(results) == 1
        assert results[0].properties["name"] == "GOLD"

    def test_no_match(self, fake_kg):
        fake_kg.add_entities(
            [{"label": "Material", "properties": {"name": "gold"}}],
        )

        results = fake_kg.get_entities("platinum")
        assert len(results) == 0


class TestNeighbours:
    def test_returns_neighbours_within_hops(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Property", "properties": {"name": "Au recovery"}},
                {"label": "Process", "properties": {"name": "flotation"}},
            ],
            session_id="s1",
            source="kb",
        )

        gold_id = None
        for n in fake_kg._nodes.values():
            if n["properties"]["name"] == "gold":
                gold_id = n["id"]
                break

        fake_kg.add_edges(
            [
                {
                    "from_label": "Material",
                    "from_name": "gold",
                    "to_label": "Property",
                    "to_name": "Au recovery",
                    "rel_type": "influences",
                    "provenance": {},
                }
            ],
            session_id="s1",
            source="kb",
        )

        results = fake_kg.neighbours(gold_id, hops=1)
        assert len(results) == 1
        assert results[0].properties["name"] == "Au recovery"

    def test_neighbours_multi_hop(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Property", "properties": {"name": "Au recovery"}},
                {"label": "Process", "properties": {"name": "flotation"}},
            ],
            session_id="s1",
            source="kb",
        )

        gold_id = None
        recovery_id = None
        for n in fake_kg._nodes.values():
            if n["properties"]["name"] == "gold":
                gold_id = n["id"]
            if n["properties"]["name"] == "Au recovery":
                recovery_id = n["id"]

        fake_kg.add_edges(
            [
                {
                    "from_label": "Material",
                    "from_name": "gold",
                    "to_label": "Property",
                    "to_name": "Au recovery",
                    "rel_type": "influences",
                    "provenance": {},
                },
                {
                    "from_label": "Property",
                    "from_name": "Au recovery",
                    "to_label": "Process",
                    "to_name": "flotation",
                    "rel_type": "measured_as",
                    "provenance": {},
                },
            ],
            session_id="s1",
            source="kb",
        )

        results = fake_kg.neighbours(gold_id, hops=2)
        assert len(results) == 2

        result_names = {r.properties["name"] for r in results}
        assert result_names == {"Au recovery", "flotation"}

    def test_start_node_not_in_results(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Property", "properties": {"name": "Au recovery"}},
            ],
            session_id="s1",
            source="kb",
        )

        gold_id = None
        for n in fake_kg._nodes.values():
            if n["properties"]["name"] == "gold":
                gold_id = n["id"]

        fake_kg.add_edges(
            [
                {
                    "from_label": "Material",
                    "from_name": "gold",
                    "to_label": "Property",
                    "to_name": "Au recovery",
                    "rel_type": "influences",
                    "provenance": {},
                }
            ],
            session_id="s1",
            source="kb",
        )

        results = fake_kg.neighbours(gold_id, hops=1)
        result_ids = {r.id for r in results}
        assert gold_id not in result_ids

    def test_no_neighbours(self, fake_kg):
        fake_kg.add_entities(
            [{"label": "Material", "properties": {"name": "isolated_node"}}],
        )

        for n in fake_kg._nodes.values():
            if n["properties"]["name"] == "isolated_node":
                results = fake_kg.neighbours(n["id"], hops=2)
                assert len(results) == 0
                break


class TestConflicts:
    def test_finds_contradicting_sources(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Source", "properties": {"id": "src1", "name": "Study A"}},
                {"label": "Source", "properties": {"id": "src2", "name": "Study B"}},
                {"label": "Source", "properties": {"id": "src3", "name": "Study C"}},
            ],
            session_id="s1",
            source="kb",
        )

        src1_id = None
        src2_id = None
        for n in fake_kg._nodes.values():
            if n["properties"]["id"] == "src1":
                src1_id = n["id"]
            if n["properties"]["id"] == "src2":
                src2_id = n["id"]

        fake_kg.add_edges(
            [
                {
                    "from_label": "Source",
                    "from_name": "Study A",
                    "to_label": "Source",
                    "to_name": "Study B",
                    "rel_type": "contradicts",
                    "provenance": {},
                }
            ],
            session_id="s1",
            source="kb",
        )

        results = fake_kg.conflicts(src1_id)
        assert len(results) == 1
        assert results[0].properties["name"] == "Study B"

    def test_no_conflicts(self, fake_kg):
        fake_kg.add_entities(
            [{"label": "Source", "properties": {"id": "src1", "name": "Study A"}}],
        )

        for n in fake_kg._nodes.values():
            if n["properties"]["id"] == "src1":
                results = fake_kg.conflicts(n["id"])
                assert len(results) == 0
                break


class TestDumpLoad:
    def test_dump_writes_json(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Property", "properties": {"name": "Au recovery"}},
            ],
            session_id="s1",
            source="kb",
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            fake_kg.dump(path)

            with open(path) as f:
                data = json.load(f)

            assert "nodes" in data
            assert "edges" in data
            assert len(data["nodes"]) == 2
            assert len(data["edges"]) == 0
        finally:
            os.unlink(path)

    def test_dump_includes_edges(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Property", "properties": {"name": "Au recovery"}},
            ],
            session_id="s1",
            source="kb",
        )

        fake_kg.add_edges(
            [
                {
                    "from_label": "Material",
                    "from_name": "gold",
                    "to_label": "Property",
                    "to_name": "Au recovery",
                    "rel_type": "influences",
                    "provenance": {"chunk_id": "c1"},
                }
            ],
            session_id="s1",
            source="kb",
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            fake_kg.dump(path)

            with open(path) as f:
                data = json.load(f)

            assert len(data["nodes"]) == 2
            assert len(data["edges"]) == 1
            assert data["edges"][0]["rel_type"] == "influences"
        finally:
            os.unlink(path)

    def test_load_restores_nodes_and_edges(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold", "density": 19.3}},
                {"label": "Property", "properties": {"name": "Au recovery"}},
            ],
            session_id="s1",
            source="kb",
        )

        fake_kg.add_edges(
            [
                {
                    "from_label": "Material",
                    "from_name": "gold",
                    "to_label": "Property",
                    "to_name": "Au recovery",
                    "rel_type": "influences",
                    "provenance": {"chunk_id": "c1"},
                }
            ],
            session_id="s1",
            source="kb",
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            fake_kg.dump(path)

            new_kg = FakeMemgraphKG()
            new_kg.load(path)

            assert len(new_kg._nodes) == 2
            assert len(new_kg._edges) == 1

            gold_nodes = new_kg.get_entities("gold")
            assert len(gold_nodes) == 1
            assert gold_nodes[0].properties["density"] == 19.3

            recovery_nodes = new_kg.get_entities("recovery")
            assert len(recovery_nodes) == 1
        finally:
            os.unlink(path)

    def test_load_preserves_edge_properties(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Process", "properties": {"name": "flotation"}},
            ],
            session_id="s1",
            source="kb",
        )

        fake_kg.add_edges(
            [
                {
                    "from_label": "Material",
                    "from_name": "gold",
                    "to_label": "Process",
                    "to_name": "flotation",
                    "rel_type": "composed_of",
                    "provenance": {"chunk_id": "c2", "confidence": 0.95},
                }
            ],
            session_id="s1",
            source="kb",
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            fake_kg.dump(path)

            new_kg = FakeMemgraphKG()
            new_kg.load(path)

            assert len(new_kg._edges) == 1
            edge = new_kg._edges[0]
            assert edge["rel_type"] == "composed_of"
            assert edge["properties"]["chunk_id"] == "c2"
            assert edge["properties"]["confidence"] == 0.95
        finally:
            os.unlink(path)


