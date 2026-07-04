from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelEntry:
    model: str
    version: str
    description: str
    schema_version: str = "1.0"
    is_default: bool = False


@dataclass
class ModelRegistry:
    models: dict[str, ModelEntry] = field(default_factory=dict)

    def register(self, name: str, entry: ModelEntry) -> None:
        self.models[name] = entry

    def get_model(self, name: str) -> ModelEntry | None:
        return self.models.get(name)

    def get_default(self) -> ModelEntry | None:
        for entry in self.models.values():
            if entry.is_default:
                return entry
        return next(iter(self.models.values()), None) if self.models else None

    def get_schema_version(self, name: str) -> str:
        entry = self.get_model(name)
        return entry.schema_version if entry else "1.0"

    def list_models(self) -> list[dict]:
        return [
            {"name": name, "model": e.model, "version": e.version, "schema_version": e.schema_version}
            for name, e in self.models.items()
        ]
