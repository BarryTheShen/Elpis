"""Small LiteLLM adapter shared by Elpis model callers.

LiteLLM handles provider-specific request/response normalization. Elpis keeps
prompt construction, structured parsing, and local budget accounting here so
all chat callers use the same behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from condenseit.providers.catalog import get_litellm_model

if TYPE_CHECKING:
    from condenseit.providers.budget import BudgetTracker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompletionResult:
    """Normalized text and usage from one LiteLLM completion."""

    content: str
    total_tokens: int
    cost_usd: float


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _message_content(message: Any) -> str:
    raw = _value(message, "content", "")
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict):
                # Keep text blocks but never leak provider reasoning blocks into
                # the digest when a provider returns a mixed content array.
                if block.get("type") in {"thinking", "redacted_thinking", "reasoning"}:
                    continue
                text = block.get("text") or block.get("content")
            else:
                text = getattr(block, "text", None) or getattr(block, "content", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _response_usage(response: Any) -> tuple[int, float]:
    usage = _value(response, "usage", {}) or {}
    total_tokens = _value(usage, "total_tokens", 0) or 0
    try:
        token_count = int(total_tokens)
    except (TypeError, ValueError):
        token_count = 0

    hidden = _value(response, "_hidden_params", {}) or {}
    cost = _value(hidden, "response_cost", None)
    if cost is None:
        cost = _value(response, "response_cost", None)
    if cost is None:
        cost = _value(usage, "cost", 0)
    try:
        cost_usd = float(cost or 0)
    except (TypeError, ValueError):
        cost_usd = 0.0
    return token_count, cost_usd


def call_litellm(
    *,
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str = "",
    base_url: str = "",
    temperature: float = 0.3,
    max_tokens: int = 1400,
    reasoning_effort: str = "none",
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 0,
    extra_headers: dict[str, str] | None = None,
    budget: BudgetTracker | None = None,
    timeout: float = 120.0,
) -> CompletionResult:
    """Call a provider through LiteLLM and normalize its response.

    ``provider`` is an Elpis provider id, not a raw LiteLLM model string. The
    adapter qualifies the model and only sends endpoint/key values when they
    are configured, which keeps local Ollama calls credential-free.
    """
    # Import lazily: admin/status requests should not load LiteLLM's large
    # provider registry until a model call is actually made.
    if budget is not None and not budget.can_spend():
        raise RuntimeError("OpenRouter daily or monthly budget exceeded")
    import litellm

    # Provider APIs vary in support for optional OpenAI parameters. LiteLLM's
    # compatibility modes safely drop unsupported fields rather than failing an
    # otherwise valid request.
    litellm.drop_params = True
    litellm.modify_params = True
    litellm.suppress_debug_info = True
    litellm.set_verbose = False

    kwargs: dict[str, Any] = {
        "model": get_litellm_model(provider, model),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "num_retries": 3,
        "stream": False,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        # LiteLLM accepts api_base for OpenAI-compatible and native providers.
        kwargs["api_base"] = base_url.rstrip("/")
    if extra_headers:
        kwargs["extra_headers"] = extra_headers
    effort = reasoning_effort.strip().lower()
    if effort and effort != "none":
        kwargs["reasoning_effort"] = effort
    if thinking_enabled:
        thinking: dict[str, Any] = {"type": "enabled"}
        if thinking_budget_tokens > 0:
            thinking["budget_tokens"] = thinking_budget_tokens
        if provider in {"openai", "custom"}:
            # The OpenAI SDK rejects unknown top-level fields. extra_body
            # preserves the thinking payload for compatible servers.
            kwargs.setdefault("extra_body", {})["thinking"] = thinking
        else:
            kwargs["thinking"] = thinking
    if provider in {"openai", "custom"} and "reasoning_effort" in kwargs:
        # LiteLLM otherwise drops this newer field because many older model
        # catalogs do not advertise it yet.
        kwargs["allowed_openai_params"] = ["reasoning_effort"]

    response = litellm.completion(**kwargs)
    choices = _value(response, "choices", []) or []
    message = _value(choices[0], "message", {}) if choices else {}
    content = _message_content(message)
    total_tokens, cost_usd = _response_usage(response)
    if budget is not None and cost_usd > 0:
        budget.record_spend(cost_usd, model=model, tokens=total_tokens)
    return CompletionResult(content, total_tokens, cost_usd)
