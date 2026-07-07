"""Model client wrappers for the minimal CodeReader Agent loop."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


DEFAULT_PROVIDER_NAME = "bailian"
DEFAULT_AGENT_MODEL = "glm-5.1"
DEFAULT_LITELLM_MODEL = "openai/glm-5.1"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_BASE_URL_ENV = "DASHSCOPE_BASE_URL"


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM runtime is not configured."""


@dataclass(frozen=True)
class ModelProviderConfig:
    """Environment-backed configuration for an OpenAI-compatible model provider."""

    provider_name: str
    model: str
    litellm_model: str
    api_key_env: str
    base_url_env: str

    @classmethod
    def bailian_glm(cls) -> "ModelProviderConfig":
        """Return the default Bailian/DashScope GLM configuration."""

        return cls(
            provider_name=DEFAULT_PROVIDER_NAME,
            model=DEFAULT_AGENT_MODEL,
            litellm_model=DEFAULT_LITELLM_MODEL,
            api_key_env=DEFAULT_API_KEY_ENV,
            base_url_env=DEFAULT_BASE_URL_ENV,
        )

    def api_key(self) -> str | None:
        """Read the provider API key from the configured environment variable."""

        return os.environ.get(self.api_key_env)

    def base_url(self) -> str | None:
        """Read the provider base URL from the configured environment variable."""

        return os.environ.get(self.base_url_env)

    def missing_environment_variables(self) -> list[str]:
        """Return required environment variable names that are currently missing."""

        missing: list[str] = []
        if not self.api_key():
            missing.append(self.api_key_env)
        if not self.base_url():
            missing.append(self.base_url_env)
        return missing

    def completion_kwargs(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Build LiteLLM completion kwargs without exposing provider secrets."""

        api_key = self.api_key()
        base_url = self.base_url()
        if not api_key or not base_url:
            missing = " or ".join(self.missing_environment_variables())
            raise LLMConfigurationError(f"Missing {missing}; cannot run LLM agent loop.")

        return {
            "model": self.litellm_model,
            "api_key": api_key,
            "api_base": base_url,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }


class LiteLLMClient:
    """Small adapter around LiteLLM's OpenAI-compatible chat completion API."""

    def __init__(
        self,
        config: ModelProviderConfig | None = None,
        model: str = DEFAULT_LITELLM_MODEL,
        api_key_env: str = DEFAULT_API_KEY_ENV,
        base_url_env: str = DEFAULT_BASE_URL_ENV,
    ) -> None:
        if (
            config is None
            and model == DEFAULT_LITELLM_MODEL
            and api_key_env == DEFAULT_API_KEY_ENV
            and base_url_env == DEFAULT_BASE_URL_ENV
        ):
            config = ModelProviderConfig.bailian_glm()
        litellm_model = model if "/" in model else f"openai/{model}"
        self.config = config or ModelProviderConfig(
            provider_name=DEFAULT_PROVIDER_NAME,
            model=litellm_model.removeprefix("openai/"),
            litellm_model=litellm_model,
            api_key_env=api_key_env,
            base_url_env=base_url_env,
        )

    def is_configured(self) -> bool:
        """Return whether required environment variables are present."""

        return not self.config.missing_environment_variables()

    def missing_environment_variables(self) -> list[str]:
        """Return missing environment variables for user-facing fallback messages."""

        return self.config.missing_environment_variables()

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        """Call the configured model with OpenAI-compatible tool definitions."""

        try:
            from litellm import completion
        except ModuleNotFoundError as exc:
            raise LLMConfigurationError("litellm is not installed; cannot run LLM agent loop.") from exc

        return completion(**self.config.completion_kwargs(messages, tools))
