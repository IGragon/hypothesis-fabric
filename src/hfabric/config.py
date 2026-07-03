from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class MVPConfig:
    # LLM
    provider: ProviderType = ProviderType.YANDEX
    model: str | None = None

    # Embeddings
    embeddings_model: str = "intfloat/multilingual-e5-small"
    embeddings_dim: int = 384

    # Retrieval
    vector_top_k: int = 20
    rerank_top_k: int = 8
    kg_hops: int = 2

    # Context budget
    context_budget_tokens: int = 16000

    # Timeouts (s)
    timeout_vector: int = 4
    timeout_kg: int = 3
    timeout_rerank: int = 8
    timeout_generate: int = 15
    timeout_export: int = 30

    # Gates
    citation_coverage_min: float = 0.5

    # Retry caps
    fe1_max_query_expansion: int = 2
    fe2_max_reprompt: int = 3
    fe6_max_cite_regenerate: int = 2

    # Scorer weights (R-A1)
    weight_novelty: float = 0.3
    weight_feasibility: float = 0.4
    weight_effect: float = 0.3

    # Memgraph
    memgraph_uri: str = "bolt://localhost:7687"

    def __post_init__(self):
        if self.model is None:
            self.model = (
                YANDEX_DEFAULT_MODEL
                if self.provider == ProviderType.YANDEX
                else ROUTERAI_DEFAULT_MODEL
            )
