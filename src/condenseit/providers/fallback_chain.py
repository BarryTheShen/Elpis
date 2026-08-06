"""Try local Ollama first, then OpenRouter."""

import logging
from typing import Any

from condenseit.network import load_network_proxy, sanitize_network_text
from condenseit.providers.base import ArticleSummary, SummarizerProvider

logger = logging.getLogger(__name__)


class FallbackChainProvider(SummarizerProvider):
    def __init__(
        self,
        primary: SummarizerProvider,
        fallback: SummarizerProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self._active = primary

    @property
    def model_name(self) -> str:
        return self._active.model_name

    def summarize_article(
        self,
        article: dict[str, Any],
    ) -> ArticleSummary:
        for provider in (self.primary, self.fallback):
            try:
                result = provider.summarize_article(article)
                self._active = provider
                return result
            except Exception as exc:
                error = sanitize_network_text(str(exc), load_network_proxy())
                logger.error(
                    "Provider %s failed for summarize_article: %s",
                    provider.model_name,
                    error,
                )
        raise RuntimeError("All LLM providers failed")

    def generate_digest(
        self,
        categorized: dict[str, list[dict[str, Any]]],
        changes: list[dict[str, str]] | None = None,
        videos: list[dict[str, Any]] | None = None,
    ) -> str:
        for provider in (self.primary, self.fallback):
            try:
                result = provider.generate_digest(categorized, changes, videos)
                self._active = provider
                return result
            except Exception as exc:
                error = sanitize_network_text(str(exc), load_network_proxy())
                logger.error(
                    "Provider %s failed for generate_digest: %s",
                    provider.model_name,
                    error,
                )
        raise RuntimeError("All LLM providers failed")
