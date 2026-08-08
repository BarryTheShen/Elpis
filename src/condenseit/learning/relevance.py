"""Deterministic relevance gating and candidate metadata serialization.

The preference engine deliberately scores a broad pool using title and body
signals.  This module supplies the publication gate that keeps incidental
body-only keyword hits out of the digest while retaining every eligible ranked
candidate for review.
"""

from __future__ import annotations

import html
import math
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from numbers import Real
from typing import Any

DEFAULT_LEAD_CONTEXT_CHARS = 500
DEFAULT_LEARNED_SIGNAL_THRESHOLD = 1.0

# These are preference signals rather than configured intent signals.  A
# sufficiently strong positive signal from a rated/read profile can rescue an
# article whose configured topic term is absent from its title and lead.
_LEARNED_SIGNAL_KEYS = frozenset(
    {
        "term_overlap",
        "bigram_overlap",
        "tfidf_cosine",
        "category",
        "source",
        "implicit_content",
        "implicit_category",
        "implicit_source",
        "synonym_boost",
        "embedding_similarity",
        "topic_score",
        "llm_rerank",
    },
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _normalise_term(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().split())


def _iter_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    return []


def _intent_terms(
    initial_keywords: Mapping[str, Sequence[str]] | None,
    topic_synonyms: Mapping[str, Sequence[str]] | None,
) -> list[str]:
    """Return configured intent terms in deterministic, de-duplicated order.

    ``topic_synonyms`` groups may use either their mapping key or values as a
    topic label.  Including both makes older config files and labels written
    by the preferences UI equivalent for the gate.
    """
    configured: list[str] = []
    if initial_keywords:
        for bucket in ("high", "medium"):
            configured.extend(
                _normalise_term(value)
                for value in _iter_values(initial_keywords.get(bucket, []))
            )

    groups: list[list[str]] = []
    if topic_synonyms:
        for label, values in topic_synonyms.items():
            group: list[str] = []
            for value in [label, *_iter_values(values)]:
                term = _normalise_term(value)
                if term and term not in group:
                    group.append(term)
            if group:
                groups.append(group)

    synonym_map: dict[str, list[str]] = {}
    for group in groups:
        for member in group:
            synonym_map[member] = group

    terms: list[str] = []
    for term in configured:
        if not term:
            continue
        for candidate in synonym_map.get(term, [term]):
            if candidate not in terms:
                terms.append(candidate)
    return terms


@lru_cache(maxsize=1024)
def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Compile a case-insensitive, boundary-aware keyword pattern."""
    escaped = re.escape(keyword).replace(r"\ ", r"\s+")
    # Preserve the existing wildcard convention (e.g. ``CVE-*``), while the
    # surrounding lookarounds prevent a short plain term from matching inside
    # a larger word such as ``go`` in ``Google``.
    escaped = escaped.replace(r"\*", r".*?")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _keyword_matches(keyword: str, text: str) -> bool:
    term = _normalise_term(keyword)
    return bool(term and _keyword_pattern(term).search(text))


def _lead_context(article: Mapping[str, Any], lead_chars: int) -> str:
    """Return bounded lead/description text, never the complete article body."""
    limit = max(1, int(lead_chars))
    # Collector-specific lead/summary fields are preferred when available.
    lead_parts: list[str] = []
    for field in ("lead", "summary", "description"):
        value = str(article.get(field) or "").strip()
        if value:
            lead_parts.append(value)
    content = str(article.get("content") or "").strip()
    if content:
        lead_parts.append(content)
    text = html.unescape(" ".join(lead_parts))
    return _HTML_TAG_RE.sub(" ", text)[:limit].lower()


def _strong_learned_signal(
    article: Mapping[str, Any],
    threshold: float,
) -> bool:
    """Return whether numeric learned preference evidence is substantial."""
    if article.get("learned_personal_signal") is True:
        return True
    breakdown = article.get("score_breakdown")
    if not isinstance(breakdown, Mapping):
        return False
    positive = 0.0
    for key in _LEARNED_SIGNAL_KEYS:
        value = breakdown.get(key)
        if isinstance(value, Real) and not isinstance(value, bool):
            number = float(value)
            if math.isfinite(number) and number > 0:
                positive += number
    return positive >= threshold


def evaluate_relevance(
    article: Mapping[str, Any],
    initial_keywords: Mapping[str, Sequence[str]] | None,
    topic_synonyms: Mapping[str, Sequence[str]] | None = None,
    *,
    lead_chars: int = DEFAULT_LEAD_CONTEXT_CHARS,
    learned_signal_threshold: float = DEFAULT_LEARNED_SIGNAL_THRESHOLD,
) -> tuple[bool, dict[str, Any]]:
    """Evaluate one ranked article and return ``(eligible, evidence)``.

    When configured intent terms exist, a term must occur in the title or a
    bounded lead context.  Body-only occurrences are intentionally ignored.
    If no intent terms are configured, the gate is open for general discovery.
    """
    terms = _intent_terms(initial_keywords, topic_synonyms)
    if not terms:
        return True, {
            "matched_terms": [],
            "title_matches": [],
            "context_matches": [],
            "relevance_reason": "no_configured_keywords",
            "selected": False,
        }

    title = str(article.get("title") or "").lower()
    context = _lead_context(article, lead_chars)
    title_matches = [term for term in terms if _keyword_matches(term, title)]
    context_matches = [term for term in terms if _keyword_matches(term, context)]
    matched_terms = list(dict.fromkeys([*title_matches, *context_matches]))

    if title_matches:
        eligible = True
        reason = "title_keyword"
    elif context_matches:
        eligible = True
        reason = "lead_keyword"
    elif _strong_learned_signal(article, learned_signal_threshold):
        eligible = True
        reason = "learned_personal_signal"
    else:
        eligible = False
        reason = "no_title_or_lead_keyword"

    return eligible, {
        "matched_terms": matched_terms,
        "title_matches": title_matches,
        "context_matches": context_matches,
        "relevance_reason": reason,
        "selected": False,
    }


def apply_relevance_gate(
    ranked: list[dict[str, Any]],
    initial_keywords: Mapping[str, Sequence[str]] | None,
    topic_synonyms: Mapping[str, Sequence[str]] | None = None,
    *,
    lead_chars: int = DEFAULT_LEAD_CONTEXT_CHARS,
    learned_signal_threshold: float = DEFAULT_LEARNED_SIGNAL_THRESHOLD,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split ranked articles into eligible and rejected lists.

    Evidence is attached under a private key for the orchestrator's candidate
    serializer.  The original article dictionaries are retained so selected
    summary behavior and ordering remain unchanged.
    """
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for article in ranked:
        is_eligible, evidence = evaluate_relevance(
            article,
            initial_keywords,
            topic_synonyms,
            lead_chars=lead_chars,
            learned_signal_threshold=learned_signal_threshold,
        )
        article["_relevance_evidence"] = evidence
        if is_eligible:
            eligible.append(article)
        else:
            rejected.append(article)
    return eligible, rejected


def _excerpt(article: Mapping[str, Any], max_chars: int) -> str:
    raw = str(
        article.get("excerpt")
        or article.get("description")
        or article.get("lead")
        or article.get("content")
        or ""
    )
    text = _HTML_TAG_RE.sub(" ", html.unescape(raw))
    text = " ".join(text.split())
    limit = max(1, int(max_chars))
    if len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def _numeric_breakdown(value: Any) -> dict[str, int | float]:
    if not isinstance(value, Mapping):
        return {}
    clean: dict[str, int | float] = {}
    for key, raw in value.items():
        if isinstance(raw, Real) and not isinstance(raw, bool):
            number = float(raw)
            if math.isfinite(number):
                clean[str(key)] = number
    return clean


def _safe_evidence(value: Any, selected: bool) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}

    def terms(key: str) -> list[str]:
        raw = source.get(key, [])
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, Sequence):
            return []
        return list(dict.fromkeys(str(item) for item in raw if str(item).strip()))

    return {
        "matched_terms": terms("matched_terms"),
        "title_matches": terms("title_matches"),
        "context_matches": terms("context_matches"),
        "relevance_reason": str(source.get("relevance_reason") or ""),
        "selected": bool(selected),
    }


def serialize_candidate(
    article: Mapping[str, Any],
    rank: int,
    *,
    selected: bool = False,
    evidence: Mapping[str, Any] | None = None,
    kind: str | None = None,
    excerpt_chars: int = 320,
) -> dict[str, Any]:
    """Return the sanitized candidate shape shared by stats and APIs."""
    raw_score = article.get("preference_score")
    score = (
        float(raw_score)
        if isinstance(raw_score, Real)
        and not isinstance(raw_score, bool)
        and math.isfinite(float(raw_score))
        else 0.0
    )
    return {
        "rank": int(rank),
        "url": str(article.get("url") or ""),
        "title": str(article.get("title") or ""),
        "source": str(article.get("source") or ""),
        "category": str(article.get("category") or "General"),
        "kind": str(kind or article.get("kind") or "article"),
        "published_at": str(article.get("published_at") or ""),
        "excerpt": _excerpt(article, excerpt_chars),
        "preference_score": score,
        "score_breakdown": _numeric_breakdown(article.get("score_breakdown")),
        "evidence": _safe_evidence(
            (
                evidence
                if evidence is not None
                else article.get("_relevance_evidence")
                or article.get("evidence")
            ),
            selected,
        ),
    }


# Readable aliases for callers that prefer a noun-based helper name.
filter_relevant_candidates = apply_relevance_gate
serialize_candidate_item = serialize_candidate

__all__ = [
    "DEFAULT_LEAD_CONTEXT_CHARS",
    "DEFAULT_LEARNED_SIGNAL_THRESHOLD",
    "apply_relevance_gate",
    "evaluate_relevance",
    "filter_relevant_candidates",
    "serialize_candidate",
    "serialize_candidate_item",
]
