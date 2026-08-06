"""Build the configured LiteLLM-backed summarizer."""

from condenseit.config import AppConfig
from condenseit.providers.base import SummarizerProvider
from condenseit.providers.budget import BudgetTracker
from condenseit.providers.catalog import (
    get_provider_base_url,
    get_provider_spec,
)
from condenseit.providers.fallback_chain import FallbackChainProvider
from condenseit.providers.litellm_provider import LiteLLMSummarizer
from condenseit.providers.openrouter_models import pick_cheapest_text_model
from condenseit.store.database import ContentStore
from condenseit.store.secure_keys import SecureKeyStore


def build_summarizer(
    config: AppConfig,
    store: ContentStore,
    digest_run_id: str = "",
    *,
    allow_unconfigured: bool = False,
) -> SummarizerProvider:
    """Build the active provider or the configured local/cloud fallback chain."""
    keys = SecureKeyStore(store)
    selected = config.llm.provider.strip().lower()
    stored_model = store.get_setting("model", "").strip()

    def model_for(provider: str) -> str:
        if stored_model:
            return stored_model
        if provider == "openrouter" and config.llm.openrouter_model.strip():
            return config.llm.openrouter_model.strip()
        if provider in {"openai", "custom"} and config.llm.openai_model.strip():
            return config.llm.openai_model.strip()
        return config.model.strip()

    def build_one(
        provider: str,
        *,
        budget: BudgetTracker | None = None,
    ) -> LiteLLMSummarizer:
        spec = get_provider_spec(provider)
        if spec is None:
            raise ValueError(f"Unknown llm.provider: {provider}")
        key = keys.get_key(spec.key_service) or ""
        if provider == "openrouter":
            key = key or config.llm.openrouter_api_key
        elif provider in {"openai", "custom"}:
            key = key or config.llm.openai_api_key
        if spec.requires_api_key and not key and not allow_unconfigured:
            raise ValueError(
                f"{spec.label} API key required (set it in Admin > Providers)"
            )
        base_url = get_provider_base_url(config, provider)
        if provider == "custom" and not base_url and not allow_unconfigured:
            raise ValueError(
                "Custom OpenAI-compatible base URL required "
                "(set it in Admin > Providers)"
            )
        return LiteLLMSummarizer(
            provider=provider,
            model=model_for(provider),
            base_url=base_url,
            api_key=key,
            max_key_takeaways=config.max_key_takeaways,
            max_summary_paragraphs=config.max_summary_paragraphs,
            digest_language=config.digest_language,
            reasoning_effort=config.llm.reasoning_effort,
            thinking_enabled=config.llm.thinking_enabled,
            thinking_budget_tokens=config.llm.thinking_budget_tokens,
            budget=budget,
        )

    if selected == "fallback":
        or_key = keys.get_key("openrouter") or config.llm.openrouter_api_key
        if not or_key and not allow_unconfigured:
            raise ValueError(
                "Fallback mode requires an OpenRouter API key "
                "(set it in Admin > Providers)"
            )
        budget = BudgetTracker(
            store,
            config.llm.openrouter_daily_budget_usd,
            config.llm.openrouter_monthly_budget_usd,
            digest_run_id=digest_run_id,
        )
        cloud = build_one("openrouter", budget=budget)
        if config.llm.openrouter_pick_cheapest:
            picked = pick_cheapest_text_model()
            if picked:
                cloud.model = picked
        return FallbackChainProvider(build_one("ollama"), cloud)

    spec = get_provider_spec(selected)
    if spec is None:
        raise ValueError(f"Unknown llm.provider: {selected}")

    budget = None
    if selected == "openrouter":
        key = keys.get_key("openrouter") or config.llm.openrouter_api_key
        if key:
            budget = BudgetTracker(
                store,
                config.llm.openrouter_daily_budget_usd,
                config.llm.openrouter_monthly_budget_usd,
                digest_run_id=digest_run_id,
            )
    summarizer = build_one(selected, budget=budget)
    if selected == "openrouter" and config.llm.openrouter_pick_cheapest:
        picked = pick_cheapest_text_model()
        if picked:
            summarizer.model = picked
    return summarizer
