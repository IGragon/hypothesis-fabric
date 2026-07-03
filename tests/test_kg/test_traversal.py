from __future__ import annotations

from hfabric.kg.traversal import bfs_traverse
from tests.test_kg.conftest import FakeMemgraphKG


class TestBFSTraverse:
    def test_delegates_to_neighbours(self, fake_kg):
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

        results = bfs_traverse(fake_kg, gold_id, hops=1)
        assert len(results) == 1
        assert results[0].properties["name"] == "Au recovery"

    def test_custom_hops(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Property", "properties": {"name": "Au recovery"}},
                {"label": "Process", "properties": {"name": "flotation"}},
                {"label": "Parameter", "properties": {"name": "pH"}},
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
                {
                    "from_label": "Process",
                    "from_name": "flotation",
                    "to_label": "Parameter",
                    "to_name": "pH",
                    "rel_type": "measured_as",
                    "provenance": {},
                },
            ],
            session_id="s1",
            source="kb",
        )

        gold_id = None
        for n in fake_kg._nodes.values():
            if n["properties"]["name"] == "gold":
                gold_id = n["id"]
                break

        results_1 = bfs_traverse(fake_kg, gold_id, hops=1)
        assert len(results_1) == 1

        results_3 = bfs_traverse(fake_kg, gold_id, hops=3)
        assert len(results_3) == 3

    def test_default_hops(self, fake_kg):
        fake_kg.add_entities(
            [
                {"label": "Material", "properties": {"name": "gold"}},
                {"label": "Property", "properties": {"name": "Au recovery"}},
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

        gold_id = None
        for n in fake_kg._nodes.values():
            if n["properties"]["name"] == "gold":
                gold_id = n["id"]
                break

        results = bfs_traverse(fake_kg, gold_id)
        assert len(results) == 2
