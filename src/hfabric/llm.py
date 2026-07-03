from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


def _yandex_model_uri(folder_id: str, model: str) -> str:
    if "://" in model:
        return model
    if "/" in model:
        return f"gpt://{folder_id}/{model}"
    return f"gpt://{folder_id}/{model}/latest"


def create_chat_model(provider_type: str, model: str) -> BaseChatModel:
    from hfabric.config import ProviderType

    pt = ProviderType(provider_type)

    if pt == ProviderType.YANDEX:
        folder_id = os.environ["YC_FOLDER_ID"]
        return ChatOpenAI(
            model=_yandex_model_uri(folder_id, model),
            api_key=os.environ["YC_API_KEY"],
            base_url="https://ai.api.cloud.yandex.net/v1",
            default_headers={"x-folder-id": folder_id},
        )

    if pt == ProviderType.ROUTERAI:
        return ChatOpenAI(
            model=model,
            api_key=os.environ["ROUTERAI_API_KEY"],
            base_url="https://routerai.ru/api/v1",
        )

    raise ValueError(f"Unknown provider: {provider_type}")
