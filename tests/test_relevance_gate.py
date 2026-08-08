"""Focused deterministic relevance-gate and candidate metadata tests."""

from __future__ import annotations

from condenseit.learning.relevance import (
    apply_relevance_gate,
    evaluate_relevance,
    serialize_candidate,
)


def _article(index: int, title: str, content: str) -> dict[str, object]:
    return {
        "url": f"https://example.test/{index}",
        "title": title,
        "content": content,
        "source": "Example",
        "category": "Technology",
        "published_at": "2026-08-08T00:00:00+00:00",
        "preference_score": float(100 - index),
        "score_breakdown": {
            "keyword_high": 2.0,
            "term_overlap": 0.25,
            "llm_reason": "must not be exposed",
        },
    }


def test_wired_tv_body_only_keyword_hits_are_rejected() -> None:
    article = _article(
        1,
        "Wired TV: what to watch this week",
        ("A review of television releases and streaming culture. " * 20)
        + "Security, Go, and drone stories are mentioned in the body.",
    )

    eligible, evidence = evaluate_relevance(
        article,
        {"high": ["security", "kubernetes"], "medium": ["go", "drone"]},
    )

    assert eligible is False
    assert evidence["matched_terms"] == []
    assert evidence["title_matches"] == []
    assert evidence["context_matches"] == []
    assert evidence["relevance_reason"] == "no_title_or_lead_keyword"


def test_title_security_story_and_configured_synonym_pass() -> None:
    article = _article(
        2,
        "K8s security hardening closes a critical vulnerability",
        "Platform maintainers published the remediation timeline.",
    )

    eligible, evidence = evaluate_relevance(
        article,
        {"high": ["kubernetes", "security"], "medium": []},
        {"kubernetes": ["k8s", "kubectl"]},
    )

    assert eligible is True
    assert "k8s" in evidence["title_matches"]
    assert "security" in evidence["title_matches"]
    assert evidence["relevance_reason"] == "title_keyword"


def test_broad_ranked_candidates_keep_order_and_no_keyword_fallback_is_open() -> None:
    ranked = [
        _article(index, f"Kubernetes security report {index}", "lead")
        for index in range(8)
    ]


    ranked.append(
        _article(
            99,
            "General culture report",
            ("Nothing relevant in this lead. " * 30) + "Kubernetes security",
        )
    )

    eligible, rejected = apply_relevance_gate(
        ranked,
        {"high": ["kubernetes", "security"], "medium": []},
    )
    assert [row["url"] for row in eligible] == [
        f"https://example.test/{index}" for index in range(8)
    ]
    assert [row["url"] for row in rejected] == ["https://example.test/99"]

    open_eligible, open_rejected = apply_relevance_gate(
        ranked,
        {"high": [], "medium": []},
    )
    assert len(open_eligible) == len(ranked)
    assert open_rejected == []


def test_candidate_metadata_marks_selection_and_strips_non_numeric_evidence() -> None:
    article = _article(3, "Kubernetes security update", "A bounded excerpt.")
    article["_relevance_evidence"] = {
        "matched_terms": ["kubernetes", "security"],
        "title_matches": ["kubernetes", "security"],
        "context_matches": [],
        "relevance_reason": "title_keyword",
        "selected": False,
    }

    candidate = serialize_candidate(article, 4, selected=True)

    assert candidate["rank"] == 4
    assert candidate["evidence"]["selected"] is True
    assert candidate["evidence"]["matched_terms"] == ["kubernetes", "security"]
    assert candidate["score_breakdown"] == {
        "keyword_high": 2.0,
        "term_overlap": 0.25,
    }
    assert len(candidate["excerpt"]) < len(str(article["content"])) + 1
    assert "must not be exposed" not in str(candidate)


def test_short_keyword_uses_token_boundaries() -> None:
    eligible, _ = evaluate_relevance(
        _article(5, "Google announces a new release", ""),
        {"high": [], "medium": ["go"]},
    )
    assert eligible is False

def test_strong_learned_personal_signal_can_rescue_missing_intent_term() -> None:
    article = _article(6, "A deeply related platform report", "No configured terms.")
    article["score_breakdown"] = {
        "term_overlap": 0.8,
        "tfidf_cosine": 0.35,
    }

    eligible, evidence = evaluate_relevance(
        article,
        {"high": ["kubernetes"], "medium": []},
    )

    assert eligible is True
    assert evidence["matched_terms"] == []
    assert evidence["relevance_reason"] == "learned_personal_signal"
