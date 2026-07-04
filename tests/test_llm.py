from __future__ import annotations

from unittest.mock import patch

from hfabric.llm import create_chat_model
from hfabric.config import ProviderType


class TestCreateChatModel:
    def test_default_temperature_is_zero(self):
        with patch("os.environ", {"YC_FOLDER_ID": "fake", "YC_API_KEY": "fake"}):
            model = create_chat_model(ProviderType.YANDEX, "test-model")
            assert model.temperature == 0.0

    def test_local_provider_returns_runtime(self):
        from hfabric.llm import LocalLLMRuntime

        runtime = create_chat_model(ProviderType.LOCAL, "local/model")
        assert isinstance(runtime, LocalLLMRuntime)
        assert runtime.temperature == 0.0

    def test_deepseek_provider_config(self):
        with patch("os.environ", {"DEEPSEEK_API_KEY": "fake-key"}):
            from langchain_openai import ChatOpenAI
            model = create_chat_model(ProviderType.DEEPSEEK, "deepseek-chat")
            assert isinstance(model, ChatOpenAI)
            assert model.temperature == 0.0
            assert "deepseek.com" in model.openai_api_base

    def test_proxyapi_provider_config(self):
        with patch("os.environ", {"PROXY_API_KEY": "fake-key"}):
            from langchain_openai import ChatOpenAI
            model = create_chat_model(ProviderType.PROXYAPI, "openai/gpt-4o")
            assert isinstance(model, ChatOpenAI)
            assert "proxyapi" in model.openai_api_base
