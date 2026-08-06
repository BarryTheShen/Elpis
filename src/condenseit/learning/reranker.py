"""LLM-based article reranker (Phase 3).

After classical + embedding scoring, a single cheap LLM call reorders the
top-K candidates using a compact reader profile narrative. The LLM score is
blended with the classical score so a bad LLM response cannot completely
override sane defaults.

Cost: ~1 call per digest run, ~5K tokens in / ~500 out.
Recommended model: qwen/qwen3.5-flash-02-23 (~$0.001/digest run on OpenRouter).
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from condenseit.learning.preference_engine import PreferenceEngine
    from condenseit.providers.budget import BudgetTracker


from condenseit.network import load_network_proxy, safe_network_error
from condenseit.providers.litellm_client import call_litellm

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL | re.IGNORECASE)
_BRACKET_RE = re.compile(r"\[.*\]", re.DOTALL)
# Reasoning models (Qwen3, DeepSeek-R1, etc.) emit <think>...</think> before output.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def build_profile_narrative(
    engine: PreferenceEngine,
    *,
    profile_summary: str = "",
    extra_dislikes: list[str] | None = None,
) -> str:
    """Build a compact plain-text reader profile from learned preferences.

    ``profile_summary`` is the reader's free-text onboarding description; when
    present it is placed first so the model has high-level intent even before
    enough ratings exist. ``extra_dislikes`` are explicit "never show me this"
    topics surfaced as an avoid list.

    Keeps output under ~300 tokens so it fits cheaply in every prompt. Returns
    an empty string only when there is nothing at all to say about the reader.
    """
    engine.learn_from_ratings()

    liked_terms = [t for t, _ in engine._liked_terms.most_common(10)]
    disliked_terms = [t for t, _ in engine._disliked_terms.most_common(8)]
    liked_cats = sorted(
        ((c, s) for c, s in engine._category_scores.items() if s > 0.3),
        key=lambda x: x[1],
        reverse=True,
    )[:4]
    disliked_cats = sorted(
        ((c, s) for c, s in engine._category_scores.items() if s < -0.3),
        key=lambda x: x[1],
    )[:3]
    liked_srcs = sorted(
        ((s, v) for s, v in engine._source_scores.items() if v > 0.5),
        key=lambda x: x[1],
        reverse=True,
    )[:3]
    disliked_srcs = sorted(
        ((s, v) for s, v in engine._source_scores.items() if v < -0.5),
        key=lambda x: x[1],
    )[:3]

    parts: list[str] = []
    if profile_summary.strip():
        parts.append(f"Reader summary: {profile_summary.strip()}")
    if liked_terms:
        parts.append(f"Likes: {', '.join(liked_terms)}")
    if disliked_terms:
        parts.append(f"Dislikes: {', '.join(disliked_terms)}")
    avoid_topics = [d.strip() for d in (extra_dislikes or []) if d.strip()]
    if avoid_topics:
        parts.append(f"Never show topics: {', '.join(avoid_topics)}")
    if liked_cats:
        cats_str = ", ".join(f"{c} (+{s:.1f})" for c, s in liked_cats)
        parts.append(f"Preferred categories: {cats_str}")
    if disliked_cats:
        cats_str = ", ".join(f"{c} ({s:.1f})" for c, s in disliked_cats)
        parts.append(f"Avoided categories: {cats_str}")
    if liked_srcs:
        parts.append(f"Liked sources: {', '.join(s for s, _ in liked_srcs)}")
    if disliked_srcs:
        parts.append(f"Disliked sources: {', '.join(s for s, _ in disliked_srcs)}")

    return "\n".join(parts)


def _build_rerank_prompt(candidates: list[dict[str, Any]], profile: str) -> str:
    articles_json = json.dumps(
        [
            {
                "url": str(a.get("url", "")),
                "title": str(a.get("title", "")),
                "category": str(a.get("category", "")),
                "source": str(a.get("source", "")),
                "snippet": str(a.get("content") or "")[:200],
            }
            for a in candidates
        ],
        ensure_ascii=False,
    )
    return (
        "You are a news relevance ranker. Given a reader profile and a list of "
        "articles, return ONLY a JSON array where each element has:\n"
        '  {"url": "<article url>", "relevance": <float 0.0-1.0>, "reason": "<5 words max>"}\n\n'  # noqa: E501
        f"Reader profile:\n{profile}\n\n"
        f"Articles:\n{articles_json}\n\n"
        "JSON array (one entry per article, same length as input):"
    )


def _parse_rerank_response(raw: str) -> dict[str, tuple[float, str]]:
    """Parse the LLM rerank response into a {url: (relevance, reason)} map."""
    # Strip reasoning-model thinking blocks before any JSON search.
    text = _THINK_RE.sub("", raw or "").strip()

    candidates: list[str] = [text]
    m = _FENCE_RE.search(text)
    if m:
        candidates.insert(0, m.group(1))
    m2 = _BRACKET_RE.search(text)
    if m2:
        candidates.append(m2.group(0))
    # Partial-JSON fallback: if the response was truncated before the closing
    # bracket (max_tokens hit), close the array and try to parse what we have.
    if text.startswith("[") and not text.rstrip().endswith("]"):
        # Strip the last (incomplete) item and close the array.
        last_complete = text.rfind("},")
        if last_complete != -1:
            candidates.append(text[: last_complete + 1] + "]")

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if not isinstance(data, list):
                continue
            result: dict[str, tuple[float, str]] = {}
            for item in data:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "")).strip()
                if not url:
                    continue
                try:
                    rel = max(0.0, min(1.0, float(item.get("relevance", 0.5) or 0.5)))
                except (TypeError, ValueError):
                    rel = 0.5
                reason = str(item.get("reason", "") or "").strip()[:200]
                result[url] = (rel, reason)
            if result:
                return result
        except (json.JSONDecodeError, ValueError):
            continue

    return {}


def _call_litellm(
    prompt: str,
    model: str,
    provider: str,
    api_key: str = "",
    base_url: str = "",
    reasoning_effort: str = "none",
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 0,
    budget: BudgetTracker | None = None,
) -> str:
    headers = (
        {
            "HTTP-Referer": "https://github.com/BarryTheShen/Elpis",
            "X-Title": "Elpis",
        }
        if provider == "openrouter"
        else None
    )
    result = call_litellm(
        provider=provider,
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a relevance ranker. Respond ONLY with a JSON array. "
                    "No markdown, no code fences, no extra text, no thinking."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
        max_tokens=2500,
        reasoning_effort=reasoning_effort,
        thinking_enabled=thinking_enabled,
        thinking_budget_tokens=thinking_budget_tokens,
        extra_headers=headers,
        budget=budget,
    )
    return result.content


def rerank(
    articles: list[dict[str, Any]],
    profile_narrative: str,
    *,
    model: str,
    provider: str,
    api_key: str = "",
    base_url: str = "",
    reasoning_effort: str = "none",
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 0,
    top_k: int = 30,
    blend: float = 0.4,
    budget: BudgetTracker | None = None,
) -> list[dict[str, Any]]:
    """Reorder articles with one LiteLLM call and blend scores."""
    if not articles or not profile_narrative:
        return articles

    candidates = articles[:top_k]
    rest = articles[top_k:]
    prompt = _build_rerank_prompt(candidates, profile_narrative)

    try:
        if not provider:
            return articles
        raw = _call_litellm(
            prompt,
            model,
            provider,
            api_key=api_key,
            base_url=base_url,
            reasoning_effort=reasoning_effort,
            thinking_enabled=thinking_enabled,
            thinking_budget_tokens=thinking_budget_tokens,
            budget=budget,
        )
        scores = _parse_rerank_response(raw)
        if not scores:
            logger.warning(
                "Reranker returned empty/unparseable response; skipping. "
                "Raw response (first 500 chars): %r",
                raw[:500],
            )
            return articles

        reranked = _apply_blend(candidates, scores, blend)
        reranked.sort(key=lambda a: a.get("preference_score", 0.0), reverse=True)
        return reranked + rest

    except Exception as exc:
        logger.warning(
            "Reranker failed, using original order: %s",
            safe_network_error(exc, load_network_proxy()),
        )
        return articles


def _apply_blend(
    candidates: list[dict[str, Any]],
    scores: dict[str, tuple[float, str]],
    blend: float,
) -> list[dict[str, Any]]:
    """Merge LLM relevance scores into each article's preference_score."""
    result = []
    for art in candidates:
        url = str(art.get("url", ""))
        classical = float(art.get("preference_score", 0.0))
        llm_rel, reason = scores.get(url, (0.5, ""))
        blended = (1.0 - blend) * classical + blend * llm_rel
        bd = dict(art.get("score_breakdown") or {})
        bd["llm_rerank"] = round(blend * llm_rel, 3)
        bd["llm_reason"] = reason
        art = {
            **art,
            "preference_score": round(blended, 3),
            "score_breakdown": bd,
        }
        result.append(art)
    return result
