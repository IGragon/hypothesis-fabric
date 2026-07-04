from __future__ import annotations

from hfabric.model_registry import ModelEntry, ModelRegistry


class TestModelRegistry:
    def test_register_and_get(self):
        reg = ModelRegistry()
        reg.register("v1", ModelEntry(model="gpt-4", version="v1", description="First version"))
        entry = reg.get_model("v1")
        assert entry is not None
        assert entry.version == "v1"

    def test_get_default(self):
        reg = ModelRegistry()
        reg.register("v1", ModelEntry(model="gpt-4", version="v1", description="V1"))
        reg.register("v2", ModelEntry(model="gpt-4o", version="v2", description="Default", is_default=True))
        default = reg.get_default()
        assert default is not None
        assert default.is_default

    def test_get_schema_version(self):
        reg = ModelRegistry()
        reg.register("v1", ModelEntry(model="gpt-4", version="v1", description="V1", schema_version="2.0"))
        assert reg.get_schema_version("v1") == "2.0"
        assert reg.get_schema_version("unknown") == "1.0"

    def test_list_models(self):
        reg = ModelRegistry()
        reg.register("v1", ModelEntry(model="gpt-4", version="v1", description="V1"))
        assert len(reg.list_models()) == 1

    def test_empty_registry_default_is_none(self):
        reg = ModelRegistry()
        assert reg.get_default() is None
