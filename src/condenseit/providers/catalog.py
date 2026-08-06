"""Provider catalog and runtime resolution helpers.

LiteLLM uses a provider/model identifier (for example ``openrouter/qwen/...``)
while Elpis keeps provider credentials and endpoint overrides in the admin
settings store.  This module is the single mapping between those contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from condenseit.config import AppConfig
    from condenseit.store.database import ContentStore


@dataclass(frozen=True)
class ProviderSpec:
    """Static metadata for one selectable model provider."""

    id: str
    label: str
    litellm_provider: str
    default_base_url: str = ""
    key_service: str = ""
    supports_base_url: bool = False
    requires_api_key: bool = True
    description: str = ""


PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="openrouter",
        label="OpenRouter",
        litellm_provider="openrouter",
        default_base_url="https://openrouter.ai/api/v1",
        key_service="openrouter",
        supports_base_url=True,
        description="One key for models from many vendors.",
    ),
    ProviderSpec(
        id="openai",
        label="OpenAI",
        litellm_provider="openai",
        default_base_url="https://api.openai.com/v1",
        key_service="openai",
        supports_base_url=True,
        description="OpenAI API and compatible hosted deployments.",
    ),
    ProviderSpec(
        id="anthropic",
        label="Anthropic",
        litellm_provider="anthropic",
        key_service="anthropic",
        supports_base_url=True,
        description="Claude models through the Anthropic API.",
    ),
    ProviderSpec(
        id="gemini",
        label="Google Gemini",
        litellm_provider="gemini",
        key_service="gemini",
        supports_base_url=True,
        description="Gemini models through Google AI Studio.",
    ),
    ProviderSpec(
        id="groq",
        label="Groq",
        litellm_provider="groq",
        default_base_url="https://api.groq.com/openai/v1",
        key_service="groq",
        supports_base_url=True,
        description="Fast hosted open-weight models.",
    ),
    ProviderSpec(
        id="mistral",
        label="Mistral",
        litellm_provider="mistral",
        default_base_url="https://api.mistral.ai/v1",
        key_service="mistral",
        supports_base_url=True,
        description="Mistral's hosted models.",
    ),
    ProviderSpec(
        id="deepseek",
        label="DeepSeek",
        litellm_provider="deepseek",
        default_base_url="https://api.deepseek.com/v1",
        key_service="deepseek",
        supports_base_url=True,
        description="DeepSeek chat and reasoning models.",
    ),
    ProviderSpec(
        id="together_ai",
        label="Together AI",
        litellm_provider="together_ai",
        default_base_url="https://api.together.xyz/v1",
        key_service="together_ai",
        supports_base_url=True,
        description="Hosted open-weight and specialist models.",
    ),
    ProviderSpec(
        id="ollama",
        label="Ollama",
        litellm_provider="ollama",
        default_base_url="http://localhost:11434",
        key_service="ollama",
        supports_base_url=True,
        requires_api_key=False,
        description="Local models managed by Ollama.",
    ),
    ProviderSpec(
        id="custom",
        label="Custom OpenAI-compatible",
        litellm_provider="openai",
        key_service="custom",
        supports_base_url=True,
        description="Any server exposing /v1/chat/completions.",
    ),
)

PROVIDER_SPEC_BY_ID = {spec.id: spec for spec in PROVIDER_SPECS}


def get_provider_spec(provider: str) -> ProviderSpec | None:
    """Return metadata for a provider id, or ``None`` for a legacy mode."""
    return PROVIDER_SPEC_BY_ID.get(provider.strip().lower())


def get_provider_base_url(config: AppConfig, provider: str) -> str:
    """Resolve a provider endpoint from DB/YAML settings and catalog defaults."""
    provider_id = provider.strip().lower()
    spec = get_provider_spec(provider_id)
    if spec is None:
        return ""

    endpoint = config.llm.providers.get(provider_id)
    if endpoint is not None and endpoint.base_url.strip():
        return endpoint.base_url.strip().rstrip("/")

    # Existing YAML/env deployments use these fields.  Keep them as a read-only
    # migration source while all new UI writes go through ``providers``.
    if provider_id == "ollama" and config.llm.ollama_host.strip():
        return config.llm.ollama_host.strip().rstrip("/")
    if provider_id == "openai" and config.llm.openai_base_url.strip():
        return config.llm.openai_base_url.strip().rstrip("/")

    return spec.default_base_url.rstrip("/")


def get_provider_model(
    config: AppConfig,
    store: ContentStore | None = None,
) -> str:
    """Return the active model, honoring live settings and old YAML names."""
    if store is not None:
        stored = store.get_setting("model", "").strip()
        if stored:
            return stored

    provider = config.llm.provider.strip().lower()
    if provider == "openrouter" and config.llm.openrouter_model.strip():
        return config.llm.openrouter_model.strip()
    if provider in {"openai", "custom"} and config.llm.openai_model.strip():
        return config.llm.openai_model.strip()
    return config.model.strip()


def get_litellm_model(provider: str, model: str) -> str:
    """Build LiteLLM's provider-qualified model identifier."""
    spec = get_provider_spec(provider)
    if spec is None:
        raise ValueError(f"Unknown model provider: {provider}")
    clean_model = model.strip()
    if not clean_model:
        raise ValueError("A model name is required")
    return f"{spec.litellm_provider}/{clean_model}"
