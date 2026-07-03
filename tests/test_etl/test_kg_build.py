from __future__ import annotations

import pytest

from hfabric.etl.kg_build import extract_edges, extract_entities


MATERIAL_TEXT = (
    "Gold recovery from pyrite and chalcopyrite ores was tested. "
    "Xanthate collectors and MIBC frother were used. "
    "Cyanide was added as a depressant during flotation."
)

PROPERTY_TEXT = (
    "The recovery of gold was 92.5%. The pH of the pulp was 10.5. "
    "The particle size P80 was 75 µm. The density was 2.8 g/cm³."
)

PARAMETER_TEXT = (
    "The dosage of collector was 50 g/t. The temperature was 25°C. "
    "The flotation time was 15 min. The pulp density was 30% solids."
)

PROCESS_TEXT = (
    "Flotation rougher and cleaner stages were used. "
    "The grinding circuit included a SAG mill and ball mill. "
    "CIL leaching was employed for gold extraction."
)

MIXED_TEXT = (
    "Gold flotation with PAX collector at a dosage of 30 g/t "
    "achieved 90% Au recovery at pH 10. The SAG mill ground "
    "chalcopyrite ore to P80 of 106 µm."
)


class TestExtractEntities:
    def test_returns_list_of_dicts(self):
        result = extract_entities("Some text.")
        assert isinstance(result, list)

    def test_extracts_material_elements(self):
        result = extract_entities("Gold and copper recovery.")
        names = [e["properties"]["name"] for e in result if e["label"] == "Material"]
        assert any("gold" in n.lower() for n in names)
        assert any("copper" in n.lower() for n in names)

    def test_extracts_material_minerals(self):
        result = extract_entities("Pyrite and chalcopyrite were present.")
        names = [e["properties"]["name"] for e in result if e["label"] == "Material"]
        assert any("pyrite" in n.lower() for n in names)
        assert any("chalcopyrite" in n.lower() for n in names)

    def test_extracts_material_reagents(self):
        result = extract_entities("Xanthate and MIBC were used as reagents.")
        names = [e["properties"]["name"] for e in result if e["label"] == "Material"]
        assert any("xanthate" in n.lower() for n in names)
        assert any("mibc" in n.lower() for n in names)

    def test_extracts_property_recovery(self):
        result = extract_entities("The recovery was 92.5%.")
        props = [e for e in result if e["label"] == "Property"]
        assert len(props) > 0

    def test_extracts_property_ph(self):
        result = extract_entities("The pH was 10.5.")
        props = [e for e in result if e["label"] == "Property" and e["properties"]["category"] == "pH"]
        assert len(props) > 0

    def test_extracts_parameter_dosage(self):
        result = extract_entities("The dosage was 50 g/t.")
        params = [e for e in result if e["label"] == "Parameter" and e["properties"]["category"] == "dosage"]
        assert len(params) > 0

    def test_extracts_parameter_temperature(self):
        result = extract_entities("The temperature was 25°C.")
        params = [e for e in result if e["label"] == "Parameter" and e["properties"]["category"] == "temperature"]
        assert len(params) > 0

    def test_extracts_process_flotation(self):
        result = extract_entities("Flotation rougher stage was used.")
        procs = [e for e in result if e["label"] == "Process" and e["properties"]["category"] == "flotation"]
        assert len(procs) > 0

    def test_extracts_process_comminution(self):
        result = extract_entities("SAG mill and ball mill were used.")
        procs = [e for e in result if e["label"] == "Process"]
        names = [p["properties"]["name"].lower() for p in procs]
        assert any("sag" in n or "ball mill" in n for n in names)

    def test_entities_have_required_keys(self):
        result = extract_entities(MIXED_TEXT)
        for entity in result:
            assert "label" in entity
            assert "properties" in entity
            assert "name" in entity["properties"]
            assert "category" in entity["properties"]

    def test_entities_no_duplicates(self):
        result = extract_entities("Gold gold gold recovery.")
        labels_names = [(e["label"], e["properties"]["name"].lower()) for e in result]
        assert len(labels_names) == len(set(labels_names))

    def test_labels_are_valid(self):
        result = extract_entities(MIXED_TEXT)
        for entity in result:
            assert entity["label"] in ("Material", "Property", "Parameter", "Process")

    def test_empty_text_returns_empty_list(self):
        result = extract_entities("")
        assert result == []


class TestExtractEdges:
    @pytest.fixture
    def sample_chunk_list(self):
        return [
            {
                "chunk_id": "chunk_0001",
                "text": MIXED_TEXT,
                "meta": {"doc_id": "doc_1", "page": 1},
            },
        ]

    def test_returns_list_of_dicts(self, sample_chunk_list):
        result = extract_edges(sample_chunk_list)
        assert isinstance(result, list)

    def test_edges_have_required_keys(self, sample_chunk_list):
        result = extract_edges(sample_chunk_list)
        for edge in result:
            assert "from_label" in edge
            assert "from_name" in edge
            assert "to_label" in edge
            assert "to_name" in edge
            assert "rel_type" in edge
            assert "provenance" in edge

    def test_edges_have_chunk_provenance(self, sample_chunk_list):
        result = extract_edges(sample_chunk_list)
        for edge in result:
            assert edge["provenance"]["chunk_id"] == "chunk_0001"
            assert edge["provenance"]["doc_id"] == "doc_1"

    def test_extracts_edges_from_mixed_text(self, sample_chunk_list):
        result = extract_edges(sample_chunk_list)
        assert len(result) > 0

    def test_material_property_edge_type(self, sample_chunk_list):
        result = extract_edges(sample_chunk_list)
        for edge in result:
            if edge["from_label"] == "Material" and edge["to_label"] == "Property":
                assert edge["rel_type"] == "influences"
            elif edge["from_label"] == "Property" and edge["to_label"] == "Material":
                assert edge["rel_type"] == "influences"

    def test_process_edges_use_influences(self, sample_chunk_list):
        result = extract_edges(sample_chunk_list)
        for edge in result:
            if edge["from_label"] == "Process" or edge["to_label"] == "Process":
                assert edge["rel_type"] == "influences"

    def test_no_duplicate_edges(self, sample_chunk_list):
        result = extract_edges(sample_chunk_list)
        pairs = [(e["from_label"], e["from_name"], e["to_label"], e["to_name"]) for e in result]
        assert len(pairs) == len(set(pairs))

    def test_edge_no_self_loops(self, sample_chunk_list):
        result = extract_edges(sample_chunk_list)
        for edge in result:
            assert not (
                edge["from_label"] == edge["to_label"]
                and edge["from_name"] == edge["to_name"]
            )

    def test_empty_chunks_returns_empty_list(self):
        result = extract_edges([])
        assert result == []

    def test_multiple_chunks_share_entities(self):
        chunks = [
            {
                "chunk_id": "chunk_0001",
                "text": "Gold flotation with PAX collector.",
                "meta": {"doc_id": "doc_1", "page": 1},
            },
            {
                "chunk_id": "chunk_0002",
                "text": "Gold recovery was high with PAX.",
                "meta": {"doc_id": "doc_1", "page": 2},
            },
        ]
        result = extract_edges(chunks)
        assert len(result) > 0
