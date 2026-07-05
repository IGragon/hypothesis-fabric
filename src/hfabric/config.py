from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ProviderType(StrEnum):
    YANDEX = "yandex"
    ROUTERAI = "routerai"
    PROXYAPI = "proxyapi"
    DEEPSEEK = "deepseek"
    LOCAL = "local"


YANDEX_DEFAULT_MODEL = "deepseek-v4-flash/latest"
ROUTERAI_DEFAULT_MODEL = "openai/gpt-4o"
PROXYAPI_DEFAULT_MODEL = "openai/gpt-4o"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
LOCAL_DEFAULT_MODEL = "local/model"


@dataclass
class MVPConfig:
    # LLM
    provider: ProviderType = ProviderType.YANDEX
    model: str | None = None
    system_prompt: str = "You are a helpful assistant."
    temperature: float = 0.2

    # Vision / VLM (B7 multimodal parsing)
    vision_model: str | None = None
    vision_provider: str | None = None
    enable_vlm: bool = True
    enable_ocr: bool = True
    enable_ocr_structuring: bool = True
    timeout_ocr_structure: int = 60

    # External grounding (B5 web search + Materials Project)
    external_search: str = "web+mp"  # "web" | "web+mp" | "none"
    external_top_k: int = 20

    # Embeddings
    embeddings_model: str = "intfloat/multilingual-e5-small"
    embeddings_dim: int = 384

    # Retrieval
    vector_top_k: int = 50
    rerank_top_k: int = 16
    kg_hops: int = 4

    # Context budget
    context_budget_tokens: int = 16000

    # Timeouts (s)
    timeout_vector: int = 4
    timeout_kg: int = 3
    timeout_rerank: int = 8
    timeout_generate: int = 120
    timeout_explain: int = 120
    timeout_explain_per_hypothesis: float = 90.0
    max_explain_hypotheses: int = 3
    explain_use_structured_output: bool = False
    explain_workers: int = 3
    timeout_export: int = 30

    # Gates
    citation_coverage_min: float = 0.5

    # Retry caps
    fe1_max_query_expansion: int = 2
    fe2_max_reprompt: int = 3
    fe6_max_cite_regenerate: int = 2

    # Scorer weights (R-A1)
    weight_novelty: float = 0.20
    weight_feasibility: float = 0.25
    weight_effect: float = 0.20
    weight_risk: float = 0.10
    weight_realizability: float = 0.10
    weight_evidence: float = 0.10
    weight_violation: float = 0.15

    # Export
    export_format: str = "json"

    # Memgraph
    memgraph_uri: str = "bolt://localhost:7687"

    # KG schema / domain patterns: path to a YAML describing node labels, edge
    # types and domain regex patterns. None => built-in metallurgy defaults
    # (kg/schema.py + kg_build.py). Enables R-K4 scalability without a core
    # rebuild.
    kg_schema_path: str | None = None

    def __post_init__(self):
        if self.model is None:
            match self.provider:
                case ProviderType.YANDEX:
                    self.model = YANDEX_DEFAULT_MODEL
                case ProviderType.ROUTERAI:
                    self.model = ROUTERAI_DEFAULT_MODEL
                case ProviderType.PROXYAPI:
                    self.model = PROXYAPI_DEFAULT_MODEL
                case ProviderType.DEEPSEEK:
                    self.model = DEEPSEEK_DEFAULT_MODEL
                case ProviderType.LOCAL:
                    self.model = LOCAL_DEFAULT_MODEL

        import os

        if self.vision_provider is None:
            self.vision_provider = os.environ.get("HFABRIC_VISION_PROVIDER") or self.provider.value
        if self.vision_model is None:
            env_vm = os.environ.get("HFABRIC_VISION_MODEL")
            if env_vm:
                self.vision_model = env_vm
            elif self.vision_provider in (ProviderType.ROUTERAI.value, ProviderType.PROXYAPI.value):
                self.vision_model = "openai/gpt-4o"
