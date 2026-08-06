"""Summarizer implementation backed by LiteLLM."""

from __future__ import annotations

from typing import Any

from condenseit.digest.format import build_digest_markdown
from condenseit.providers.base import (
    ArticleSummary,
    SummarizerProvider,
    build_chat_system_prompt,
    build_chat_user_prompt,
    parse_summary_response,
    resolve_digest_language,
)
from condenseit.providers.budget import BudgetTracker
from condenseit.providers.litellm_client import call_litellm


class LiteLLMSummarizer(SummarizerProvider):
    """Call any catalogued provider through LiteLLM's unified interface."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str = "",
        api_key: str = "",
        max_key_takeaways: int = 5,
        max_summary_paragraphs: int = 5,
        digest_language: str = "en",
        reasoning_effort: str = "none",
        thinking_enabled: bool = False,
        thinking_budget_tokens: int = 0,
        budget: BudgetTracker | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_key_takeaways = max_key_takeaways
        self.max_summary_paragraphs = max_summary_paragraphs
        self.digest_language = digest_language
        self.reasoning_effort = reasoning_effort
        self.thinking_enabled = thinking_enabled
        self.thinking_budget_tokens = thinking_budget_tokens
        self.budget = budget

    @property
    def model_name(self) -> str:
        return self.model

    def _chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1400,
    ) -> str:
        headers = (
            {
                "HTTP-Referer": "https://github.com/BarryTheShen/Elpis",
                "X-Title": "Elpis",
            }
            if self.provider == "openrouter"
            else None
        )
        result = call_litellm(
            provider=self.provider,
            model=self.model,
            messages=messages,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0.3,
            max_tokens=max_tokens,
            reasoning_effort=self.reasoning_effort,
            thinking_enabled=self.thinking_enabled,
            thinking_budget_tokens=self.thinking_budget_tokens,
            extra_headers=headers,
            budget=self.budget,
        )
        return result.content

    def summarize_article(self, article: dict[str, Any]) -> ArticleSummary:
        content = (article.get("content") or "")[:4000]
        title = article.get("title", "Untitled")
        language = resolve_digest_language(self.digest_language, content)
        messages = [
            {"role": "system", "content": build_chat_system_prompt(language)},
            {
                "role": "user",
                "content": build_chat_user_prompt(
                    title,
                    content,
                    self.max_key_takeaways,
                    self.max_summary_paragraphs,
                    language=language,
                ),
            },
        ]
        raw = self._chat(messages, max_tokens=1400)
        return parse_summary_response(raw)

    def generate_digest(
        self,
        categorized: dict[str, list[dict[str, Any]]],
        changes: list[dict[str, str]] | None = None,
        videos: list[dict[str, Any]] | None = None,
    ) -> str:
        return build_digest_markdown(categorized, changes, videos)
