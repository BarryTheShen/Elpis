"""Ranking experiments for broad RSS candidate pools.

These fixtures intentionally model many near-duplicate feed entries without
making network calls. They protect the contract that broad collection is
cheap, relevance is scored before the final digest cap, and similar coverage
can still be separated by learned source preference.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from condenseit.learning.preference_engine import PreferenceEngine
from condenseit.pipeline.article_balance import select_balanced_digest_articles
from condenseit.store.database import ContentStore


def _article(
    index: int,
    title: str,
    content: str,
    *,
    category: str = "General",
    source: str = "Feed",
) -> dict[str, str]:
    return {
        "url": f"https://candidate.example/{index}",
        "title": title,
        "content": content,
        "category": category,
        "source": source,
        "published_at": datetime.now(UTC).isoformat(),
    }


def test_large_candidate_pool_surfaces_keyword_relevant_articles(tmp_path: Path) -> None:
    """Hundreds of distractors do not bury articles matching the reader brief."""
    store = ContentStore(db_path=tmp_path / "ranking.db")
    engine = PreferenceEngine(store, min_ratings=5)
    distractors = [
        _article(i, f"Local lifestyle update {i}", "gardening recipes travel")
        for i in range(200)
    ]
    relevant = [
        _article(
            900 + i,
            f"Kubernetes CVE security bulletin {i}",
            "critical Kubernetes vulnerability and container security response",
            category="Infosec",
        )
        for i in range(5)
    ]

    ranked = engine.rank_articles(
        distractors + relevant,
        keyword_high={"kubernetes", "cve", "security"},
    )

    assert len(ranked) == 205
    assert all("Kubernetes" in row["title"] for row in ranked[:5])
    assert ranked[0]["preference_score"] > ranked[-1]["preference_score"]


def test_similar_story_variants_use_learned_source_preference(tmp_path: Path) -> None:
    """Near-identical coverage can still prefer a source the reader trusts."""
    store = ContentStore(db_path=tmp_path / "similar.db")
    for i in range(5):
        url = f"https://trusted.example/training-{i}"
        content = "Kubernetes security vulnerability response"
        store.save_article(
            {
                "url": url,
                "title": f"Kubernetes security report {i}",
                "content": content,
                "source": "Trusted Security Desk",
                "category": "Infosec",
                "content_hash": ContentStore.content_hash(content),
                "published_at": "",
                "collected_at": datetime.now(UTC).isoformat(),
            }
        )
        store.rate_article(url, 5)

    engine = PreferenceEngine(store, min_ratings=5)
    variants = [
        _article(
            1,
            "Kubernetes security vulnerability response",
            "Security researchers published a vulnerability response.",
            category="Infosec",
            source="Noisy Aggregator",
        ),
        _article(
            2,
            "Kubernetes security vulnerability response",
            "Security researchers published a vulnerability response.",
            category="Infosec",
            source="Trusted Security Desk",
        ),
    ]

    ranked = engine.rank_articles(variants)

    assert ranked[0]["source"] == "Trusted Security Desk"
    assert ranked[0]["score_breakdown"]["source"] > ranked[1]["score_breakdown"]["source"]


def test_near_duplicate_titles_keep_the_highest_ranked_version() -> None:
    """Similar coverage is collapsed only after the best version is ranked."""
    from types import SimpleNamespace

    from condenseit.pipeline.orchestrator import DigestPipeline

    pipeline = object.__new__(DigestPipeline)
    pipeline._embed_provider = None
    pipeline.config = SimpleNamespace(
        relevance=SimpleNamespace(semantic_dedup_enabled=False),
    )
    articles = [
        {
            **_article(
                1,
                "Kubernetes patches critical CVE in ingress controller",
                "security patch",
                category="Infosec",
            ),
            "preference_score": 9.0,
        },
        {
            **_article(
                2,
                "Kubernetes patches critical CVE in ingress controller",
                "security patch",
                category="Infosec",
            ),
            "preference_score": 3.0,
        },
    ]

    deduplicated = pipeline._deduplicate_stories(articles)

    assert [row["url"] for row in deduplicated] == [articles[0]["url"]]


def test_large_ranked_pool_is_reduced_to_small_digest_selection() -> None:
    """The candidate pool can be broad while the publication stays concise."""
    ranked = [
        {
            **_article(
                i,
                f"Story {i}",
                "relevant reporting",
                category=("Security" if i % 2 == 0 else "Engineering"),
            ),
            "preference_score": float(500 - i),
        }
        for i in range(250)
    ]

    selected = select_balanced_digest_articles(
        ranked,
        max_n=5,
        max_per_category=3,
    )

    assert len(selected) == 5
    assert {row["category"] for row in selected} == {"Security", "Engineering"}
    assert max(row["preference_score"] for row in selected) == 500
