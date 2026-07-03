from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProviderType(StrEnum):
    YANDEX = "yandex"
    ROUTERAI = "routerai"


YANDEX_DEFAULT_MODEL = "deepseek-v4-flash/latest"
ROUTERAI_DEFAULT_MODEL = "openai/gpt-4o"


@dataclass
class AppConfig:
    provider: ProviderType = ProviderType.YANDEX
    model: str | None = None
    system_prompt: str = "You are a helpful assistant."

    def __post_init__(self):
        if self.model is None:
            self.model = (
                YANDEX_DEFAULT_MODEL
                if self.provider == ProviderType.YANDEX
                else ROUTERAI_DEFAULT_MODEL
            )
