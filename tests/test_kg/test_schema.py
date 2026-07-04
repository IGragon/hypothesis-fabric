from __future__ import annotations

import re
from pathlib import Path

import pytest

from hfabric.kg.schema import (
    DEFAULT_EDGE_TYPES,
    DEFAULT_NODE_LABELS,
    KGSchema,
    load_schema,
)


class TestDefaults:
    def test_default_node_labels(self):
        assert "Material" in DEFAULT_NODE_LABELS
        assert "Source" in DEFAULT_NODE_LABELS

    def test_default_edge_types(self):
        assert "influences" in DEFAULT_EDGE_TYPES
        assert "contradicts" in DEFAULT_EDGE_TYPES

    def test_kg_schema_defaults_complete(self):
        s = KGSchema()
        assert s.node_labels == DEFAULT_NODE_LABELS
        assert s.edge_types == DEFAULT_EDGE_TYPES
        assert set(s.patterns.keys()) >= {"Material", "Property", "Parameter", "Process"}


class TestLoadSchema:
    def test_none_path_returns_defaults(self):
        s = load_schema(None)
        assert s.node_labels == DEFAULT_NODE_LABELS

    def test_missing_path_returns_defaults(self, tmp_path):
        s = load_schema(str(tmp_path / "nope.yaml"))
        assert s.node_labels == DEFAULT_NODE_LABELS

    def test_malformed_yaml_returns_defaults(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(":- not : valid : yaml :")
        s = load_schema(str(p))
        assert s.node_labels == DEFAULT_NODE_LABELS

    def test_yaml_overrides_node_labels_and_edge_types(self, tmp_path):
        p = tmp_path / "domain.yaml"
        p.write_text(
            "node_labels: [Polymer, Fiber, Matrix, Source]\n"
            "edge_types: [influences, reinforces]\n"
        )
        s = load_schema(str(p))
        assert "Polymer" in s.node_labels
        assert "Source" in s.node_labels
        assert "reinforces" in s.edge_types
        assert "influences" in s.edge_types

    def test_yaml_overrides_patterns(self, tmp_path):
        p = tmp_path / "patterns.yaml"
        p.write_text(
            "patterns:\n"
            "  Polymer:\n"
            "    - [polymername, \"\\\\b(PET|PLA|PA6)\\\\b\"]\n"
            "    - \"\\\\b(epoxy)\\\\b\"\n"
        )
        s = load_schema(str(p))
        poly = s.patterns["Polymer"]
        assert len(poly) == 2
        names = [m[0] for m in poly]
        assert "polymername" in names
        text = "PET and epoxy are here"
        any_match = any(m[1].search(text) for m in poly)
        assert any_match

    def test_yaml_partial_keeps_other_defaults(self, tmp_path):
        p = tmp_path / "partial.yaml"
        p.write_text("node_labels: [Polymer, Source]\n")
        s = load_schema(str(p))
        assert "Polymer" in s.node_labels
        assert "Material" not in s.node_labels
        assert "Property" in s.patterns


class TestExtractEntitiesWithPatterns:
    def test_default_patterns_still_work(self):
        from hfabric.etl.kg_build import extract_entities

        ents = extract_entities("Gold and copper recovery were measured.")
        labels = [e["label"] for e in ents]
        assert "Material" in labels

    def test_custom_patterns_override(self):
        from hfabric.etl.kg_build import extract_entities

        custom = {
            "Polymer": [("polymer_id", re.compile(r"\b(PET|PLA)\b", re.IGNORECASE))],
            "Property": [],
            "Parameter": [],
            "Process": [],
        }
        ents = extract_entities("PET and PLA samples.", patterns=custom)
        labels = {e["label"] for e in ents}
        assert labels == {"Polymer"}
        names = [e["properties"]["name"] for e in ents]
        assert any("pet" in n or "pla" in n for n in names)


class TestMemgraphKGSchemaAware:
    def test_default_labels_used(self):
        from hfabric.kg.client import MemgraphKG

        class _FakeSession:
            def __init__(self):
                self.queries = []

            def run(self, q, **kw):
                self.queries.append((q, kw))

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class _FakeDriver:
            def __init__(self):
                self._session = _FakeSession()

            def verify_connectivity(self):
                pass

            def session(self):
                return self._session

        fake_driver = _FakeDriver()

        class _KG(MemgraphKG):
            def __init__(self):
                self._driver = fake_driver
                self._node_labels = set(DEFAULT_NODE_LABELS)
                self._edge_types = set(DEFAULT_EDGE_TYPES)
                self._create_indices()

        kg = _KG()
        labels_in_idx = set()
        for q, _ in fake_driver._session.queries:
            if q.startswith("CREATE INDEX ON :"):
                labels_in_idx.add(q.split(":")[1].split("(")[0])
        assert labels_in_idx == DEFAULT_NODE_LABELS

    def test_custom_labels_indexed(self):
        from hfabric.kg.client import MemgraphKG

        class _FakeSession:
            def __init__(self):
                self.queries = []

            def run(self, q, **kw):
                self.queries.append((q, kw))

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class _FakeDriver:
            def __init__(self):
                self._session = _FakeSession()

            def verify_connectivity(self):
                pass

            def session(self):
                return self._session

        fake_driver = _FakeDriver()

        class _KG(MemgraphKG):
            def __init__(self):
                self._driver = fake_driver
                self._node_labels = {"Polymer", "Source"}
                self._edge_types = {"reinforces"}
                self._create_indices()

        kg = _KG()
        labels_in_idx = set()
        for q, _ in fake_driver._session.queries:
            if q.startswith("CREATE INDEX ON :"):
                labels_in_idx.add(q.split(":")[1].split("(")[0])
        assert labels_in_idx == {"Polymer", "Source"}
        assert kg.node_labels == {"Polymer", "Source"}
        assert kg.edge_types == {"reinforces"}


class TestMVPConfigKgSchemaPath:
    def test_config_has_kg_schema_path_default_none(self):
        from hfabric.config import MVPConfig
        c = MVPConfig()
        assert c.kg_schema_path is None

    def test_config_settable(self):
        from hfabric.config import MVPConfig
        c = MVPConfig(kg_schema_path="/tmp/x.yaml")
        assert c.kg_schema_path == "/tmp/x.yaml"