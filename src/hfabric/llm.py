from __future__ import annotations

import os
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


class _DeepSeekChatOpenAI(ChatOpenAI):
    def with_structured_output(
        self,
        schema: Any = None,
        *,
        method: str = "function_calling",
        **kwargs: Any,
    ) -> Any:
        chain = super().with_structured_output(
            schema, method=method, **kwargs
        )
        try:
            chain.steps[0].kwargs.pop("tool_choice", None)
        except Exception:
            pass
        return chain


class LocalLLMRuntime:
    def __init__(self, model_name: str = "local/model"):
        self._model_name = model_name

    def invoke(self, prompt: str) -> Any:
        class MockResponse:
            content = '{"claim": "Local model hypothesis", "mechanism": "test", "expected_effect": "+5%", "evidence_refs": ["c1"]}'
        return MockResponse()

    @property
    def temperature(self) -> float:
        return 0.0


def _yandex_model_uri(folder_id: str, model: str) -> str:
    if "://" in model:
        return model
    if "/" in model:
        return f"gpt://{folder_id}/{model}"
    return f"gpt://{folder_id}/{model}/latest"


_VLM_PROMPT = (
    "You are analysing a metallurgical process image (a flotation flow-sheet, "
    "equipment list, or process-regulation document). Extract EVERY text label, "
    "flow arrow/connection, equipment name, reagent, and numeric parameter you "
    "can see. Preserve Russian terms verbatim. Respond ONLY with JSON: "
    '{"labels": [], "flows": [], "equipment": [], "reagents": [], "params": [], '
    '"description": "2-4 sentence plain-language summary of the process"}'
)


def create_vision_chat_model(config: Any) -> BaseChatModel | None:
    if not getattr(config, "enable_vlm", True):
        return None
    vision_model = getattr(config, "vision_model", None)
    if not vision_model:
        return None
    vision_provider = getattr(config, "vision_provider", None) or config.provider
    if hasattr(vision_provider, "value"):
        vision_provider = vision_provider.value
    try:
        return create_chat_model(vision_provider, vision_model, temperature=0.0)
    except Exception:
        return None


def vlm_describe_image(model: BaseChatModel, image_b64: str, mime: str = "image/png") -> str:
    from langchain_core.messages import HumanMessage

    message = HumanMessage(
        content=[
            {"type": "text", "text": _VLM_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
        ]
    )
    response = model.invoke([message])
    content = response.content if hasattr(response, "content") else str(response)
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return content.strip()


def create_chat_model(
    provider_type: str, model: str, temperature: float = 0.0
) -> BaseChatModel:
    from hfabric.config import ProviderType

    pt = ProviderType(provider_type)

    if pt == ProviderType.YANDEX:
        folder_id = os.environ["YC_FOLDER_ID"]
        return ChatOpenAI(
            model=_yandex_model_uri(folder_id, model),
            api_key=os.environ["YC_API_KEY"],
            base_url="https://ai.api.cloud.yandex.net/v1",
            default_headers={"x-folder-id": folder_id},
            temperature=temperature,
        )

    if pt == ProviderType.ROUTERAI:
        return ChatOpenAI(
            model=model,
            api_key=os.environ["ROUTERAI_API_KEY"],
            base_url="https://routerai.ru/api/v1",
            temperature=temperature,
        )

    if pt == ProviderType.PROXYAPI:
        return ChatOpenAI(
            model=model,
            api_key=os.environ["PROXY_API_KEY"],
            base_url="https://api.proxyapi.ru/openai/v1",
            temperature=temperature,
        )

    if pt == ProviderType.DEEPSEEK:
        return _DeepSeekChatOpenAI(
            model=model,
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com/v1",
            temperature=temperature,
        )

    if pt == ProviderType.LOCAL:
        return LocalLLMRuntime(model)

    raise ValueError(f"Unknown provider: {provider_type}")
