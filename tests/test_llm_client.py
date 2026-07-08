from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from code_reader_agent.runtime.llm_client import (
    DEFAULT_AGENT_MODEL,
    DEFAULT_API_KEY_ENV,
    DEFAULT_BASE_URL_ENV,
    DEFAULT_LITELLM_MODEL,
    LLMConfigurationError,
    LiteLLMClient,
    ModelProviderConfig,
)


def test_default_model_config_uses_bailian_glm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DEFAULT_API_KEY_ENV, raising=False)
    monkeypatch.delenv(DEFAULT_BASE_URL_ENV, raising=False)

    config = ModelProviderConfig.bailian_glm()

    assert config.provider_name == "bailian"
    assert config.model == DEFAULT_AGENT_MODEL == "glm-5.1"
    assert config.litellm_model == DEFAULT_LITELLM_MODEL == "openai/glm-5.1"
    assert config.missing_environment_variables() == [DEFAULT_API_KEY_ENV, DEFAULT_BASE_URL_ENV]


def test_model_config_builds_litellm_kwargs_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEFAULT_API_KEY_ENV, "test-key")
    monkeypatch.setenv(DEFAULT_BASE_URL_ENV, "https://dashscope.example/openai-compatible/v1")
    config = ModelProviderConfig.bailian_glm()

    kwargs = config.completion_kwargs(messages=[{"role": "user", "content": "hi"}], tools=[])

    assert kwargs["model"] == "openai/glm-5.1"
    assert kwargs["api_key"] == "test-key"
    assert kwargs["api_base"] == "https://dashscope.example/openai-compatible/v1"
    assert "tool_choice" not in kwargs


def test_model_config_includes_tool_choice_when_tools_are_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEFAULT_API_KEY_ENV, "test-key")
    monkeypatch.setenv(DEFAULT_BASE_URL_ENV, "https://dashscope.example/openai-compatible/v1")

    kwargs = ModelProviderConfig.bailian_glm().completion_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "scan_project", "parameters": {}}}],
    )

    assert kwargs["tools"]
    assert kwargs["tool_choice"] == "auto"


def test_model_config_rejects_missing_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEFAULT_API_KEY_ENV, "test-key")
    monkeypatch.delenv(DEFAULT_BASE_URL_ENV, raising=False)

    with pytest.raises(LLMConfigurationError, match=DEFAULT_BASE_URL_ENV):
        ModelProviderConfig.bailian_glm().completion_kwargs(messages=[], tools=[])


def test_litellm_client_calls_openai_compatible_model(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_completion(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"choices": [{"message": {"role": "assistant", "content": "{}"}}]}

    monkeypatch.setenv(DEFAULT_API_KEY_ENV, "test-key")
    monkeypatch.setenv(DEFAULT_BASE_URL_ENV, "https://dashscope.example/openai-compatible/v1")
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))

    response = LiteLLMClient().complete(messages=[{"role": "user", "content": "hi"}], tools=[])

    assert response["choices"][0]["message"]["content"] == "{}"
    assert captured["model"] == "openai/glm-5.1"
    assert captured["api_key"] == "test-key"
    assert captured["api_base"] == "https://dashscope.example/openai-compatible/v1"


def test_litellm_client_normalizes_unprefixed_model_name() -> None:
    client = LiteLLMClient(model="glm-5.1")

    assert client.config.model == "glm-5.1"
    assert client.config.litellm_model == "openai/glm-5.1"
