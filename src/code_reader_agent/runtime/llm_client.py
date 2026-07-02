"""LLM client wrapper for the minimal CodeReader Agent loop."""

from __future__ import annotations

import os
from typing import Any


DEFAULT_AGENT_MODEL = "openai/glm-5.1"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_BASE_URL_ENV = "DASHSCOPE_BASE_URL"


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM runtime is not configured."""


class LiteLLMClient:
    """Small adapter around LiteLLM's OpenAI-compatible chat completion API."""

    def __init__(
        self,
        model: str = DEFAULT_AGENT_MODEL,
        api_key_env: str = DEFAULT_API_KEY_ENV,
        base_url_env: str = DEFAULT_BASE_URL_ENV,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.base_url_env = base_url_env

    def is_configured(self) -> bool:
        """Return whether required environment variables are present."""

        return bool(os.environ.get(self.api_key_env) and os.environ.get(self.base_url_env))

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        """Call the configured model with OpenAI-compatible tool definitions."""

        api_key = os.environ.get(self.api_key_env)
        base_url = os.environ.get(self.base_url_env)
        if not api_key or not base_url:
            raise LLMConfigurationError(
                f"Missing {self.api_key_env} or {self.base_url_env}; cannot run LLM agent loop."
            )

        try:
            from litellm import completion
        except ModuleNotFoundError as exc:
            raise LLMConfigurationError("litellm is not installed; cannot run LLM agent loop.") from exc

        return completion(
            model=self.model,
            api_key=api_key,
            api_base=base_url,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
