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
        names = [e["properties"].get("display_name", e["properties"]["name"]) for e in result if e["label"] == "Material"]
        assert any("gold" in n.lower() for n in names)
        assert any("copper" in n.lower() for n in names)

    def test_extracts_material_minerals(self):
        result = extract_entities("Pyrite and chalcopyrite were present.")
        names = [e["properties"].get("display_name", e["properties"]["name"]) for e in result if e["label"] == "Material"]
        assert any("pyrite" in n.lower() for n in names)
        assert any("chalcopyrite" in n.lower() for n in names)

    def test_extracts_material_reagents(self):
        result = extract_entities("Xanthate and MIBC were used as reagents.")
        names = [e["properties"].get("display_name", e["properties"]["name"]) for e in result if e["label"] == "Material"]
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


RUSSIAN_MATERIAL_TEXT = (
    "Извлечение золота и серебра из пиритных и халькопиритных руд было исследовано. "
    "Ксантогенатные собиратели и вспениватель МИБК использовались. "
    "Цианид добавлялся как депрессор при флотации."
)

RUSSIAN_PROPERTY_TEXT = (
    "Извлечение золота составило 92.5%. рН пульпы был 10.5. "
    "Крупность частиц P80 составила 75 мкм. Плотность составила 2.8 г/см³."
)

RUSSIAN_PARAMETER_TEXT = (
    "Расход собирателя составил 50 г/т. Температура была 25°C. "
    "Время флотации составило 15 мин. Плотность пульпы составила 30% твёрдого."
)

RUSSIAN_PROCESS_TEXT = (
    "Флотация основная и контрольная стадии использовались. "
    "Цикл измельчения включал мельницу полусамоизмельчения и шаровую мельницу. "
    "Сорбционное выщелачивание применялось для извлечения золота."
)

RUSSIAN_MIXED_TEXT = (
    "Флотация золота с ксантогенатным собирателем при расходе 30 г/т "
    "обеспечила извлечение Au 90% при рН 10. Мельница полусамоизмельчения "
    "измельчала халькопиритную руду до крупности P80 106 мкм."
)


class TestExtractEntitiesRussian:
    def test_returns_list_of_dicts(self):
        result = extract_entities("Какой-то текст.")
        assert isinstance(result, list)

    def test_extracts_russian_material_elements(self):
        result = extract_entities(RUSSIAN_MATERIAL_TEXT)
        names = [e["properties"].get("display_name", e["properties"]["name"]).lower() for e in result if e["label"] == "Material" and e["properties"]["category"].endswith("_ru")]
        assert any("золот" in n for n in names)
        assert any("серебр" in n for n in names)

    def test_extracts_russian_material_minerals(self):
        result = extract_entities(RUSSIAN_MATERIAL_TEXT)
        names = [e["properties"].get("display_name", e["properties"]["name"]).lower() for e in result if e["label"] == "Material" and e["properties"]["category"] == "mineral_ru"]
        assert any("пирит" in n for n in names)
        assert any("халькопирит" in n for n in names)

    def test_extracts_russian_material_reagents(self):
        result = extract_entities(RUSSIAN_MATERIAL_TEXT)
        names = [e["properties"].get("display_name", e["properties"]["name"]).lower() for e in result if e["label"] == "Material" and e["properties"]["category"] == "reagent_ru"]
        assert any("ксантогенат" in n for n in names)
        assert any("мибк" in n for n in names)

    def test_extracts_russian_property_recovery(self):
        result = extract_entities(RUSSIAN_PROPERTY_TEXT)
        props = [e for e in result if e["label"] == "Property" and e["properties"]["category"] == "recovery_ru"]
        assert len(props) > 0

    def test_extracts_russian_property_ph(self):
        result = extract_entities(RUSSIAN_PROPERTY_TEXT)
        props = [e for e in result if e["label"] == "Property" and e["properties"]["category"] == "pH_ru"]
        assert len(props) > 0

    def test_extracts_russian_parameter_dosage(self):
        result = extract_entities(RUSSIAN_PARAMETER_TEXT)
        params = [e for e in result if e["label"] == "Parameter" and e["properties"]["category"] == "dosage_ru"]
        assert len(params) > 0

    def test_extracts_russian_process_flotation(self):
        result = extract_entities(RUSSIAN_PROCESS_TEXT)
        procs = [e for e in result if e["label"] == "Process" and e["properties"]["category"] == "flotation_ru"]
        assert len(procs) > 0

    def test_extracts_russian_process_comminution(self):
        result = extract_entities(RUSSIAN_PROCESS_TEXT)
        procs = [e for e in result if e["label"] == "Process" and e["properties"]["category"] == "comminution_ru"]
        assert len(procs) > 0

    def test_russian_entities_have_required_keys(self):
        result = extract_entities(RUSSIAN_MATERIAL_TEXT)
        assert len(result) > 0
        for entity in result:
            assert "label" in entity
            assert "properties" in entity
            assert "name" in entity["properties"]
            assert "category" in entity["properties"]

    def test_russian_and_english_mixed_text(self):
        result = extract_entities(RUSSIAN_MIXED_TEXT)
        assert len(result) > 0

        russian_categories = {e["properties"]["category"] for e in result if e["properties"]["category"].endswith("_ru")}
        assert len(russian_categories) > 0

        english_categories = {e["properties"]["category"] for e in result if not e["properties"]["category"].endswith("_ru")}
        assert len(english_categories) > 0


from hfabric.etl.kg_build import detect_contradictions


CONTRADICTING_CHUNKS = [
    {
        "chunk_id": "c1",
        "text": "Increasing gold recovery using xanthate collectors was demonstrated.",
        "meta": {"doc_id": "d1"},
    },
    {
        "chunk_id": "c2",
        "text": "The addition of xanthate collector decreases gold recovery significantly.",
        "meta": {"doc_id": "d2"},
    },
]

NO_CONFLICT_CHUNKS = [
    {
        "chunk_id": "c1",
        "text": "Gold recovery increases with xanthate addition.",
        "meta": {"doc_id": "d1"},
    },
    {
        "chunk_id": "c2",
        "text": "Gold recovery also increases with PAX collector.",
        "meta": {"doc_id": "d2"},
    },
]

RUSSIAN_CONTRADICTING_CHUNKS = [
    {
        "chunk_id": "c_ru_1",
        "text": "Применение ксантогената повышает извлечение золота на 10%.",
        "meta": {"doc_id": "d_ru_1"},
    },
    {
        "chunk_id": "c_ru_2",
        "text": "Добавление ксантогената снижает извлечение золота при флотации.",
        "meta": {"doc_id": "d_ru_2"},
    },
]


class TestDetectContradictions:
    def test_detects_contradicting_chunks(self):
        result = detect_contradictions(CONTRADICTING_CHUNKS)
        assert len(result) > 0
        assert result[0]["rel_type"] == "contradicts"
        assert result[0]["from_name"] in ("c1", "c2")
        assert result[0]["to_name"] in ("c1", "c2")

    def test_no_conflicts_returns_empty(self):
        result = detect_contradictions(NO_CONFLICT_CHUNKS)
        assert result == []

    def test_empty_chunks_returns_empty(self):
        result = detect_contradictions([])
        assert result == []

    def test_russian_contradictions_detected(self):
        result = detect_contradictions(RUSSIAN_CONTRADICTING_CHUNKS)
        assert len(result) > 0
        assert result[0]["rel_type"] == "contradicts"

    def test_single_chunk_returns_empty(self):
        result = detect_contradictions([CONTRADICTING_CHUNKS[0]])
        assert result == []
