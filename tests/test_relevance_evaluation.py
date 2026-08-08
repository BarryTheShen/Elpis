"""Offline relevance-evaluation contract for broad ranked candidate pools.

The fixture is intentionally independent of providers and credentials.  It
exercises the deterministic gate on realistic reader profiles and keeps an
explicit gold label for every candidate so a future ranking change can be
measured rather than judged from a single example.  A candidate that contains
a configured term only in the body after the lead is an incidental negative;
near-duplicate coverage is retained as two relevant candidates because the
relevance gate is not the story-deduplication stage.

The optional live LLM judge is deliberately not part of the default test run:
use these same cases as input to an externally configured judge and compare its
labels to ``expected_relevant``.  The offline gate remains the deterministic
regression contract and must run without network access.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log2
from typing import Any

import pytest

from condenseit.learning.relevance import evaluate_relevance, serialize_candidate


@dataclass(frozen=True)
class CandidateCase:
    url: str
    title: str
    content: str
    expected_relevant: bool
    kind: str = "article"
    duplicate_of: str | None = None

    def as_article(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "source": "Fixture source",
            "category": "Technology",
            "kind": self.kind,
        }


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    query: str
    initial_keywords: dict[str, list[str]]
    topic_synonyms: dict[str, list[str]]
    candidates: tuple[CandidateCase, ...]
    expected_metrics: dict[str, float]


def _body_only(text: str) -> str:
    """Place a configured term after the deterministic 500-character lead."""
    return ("Unrelated entertainment copy. " * 24) + text


def _lead(text: str) -> str:
    """Put a configured term in the lead while leaving the title generic."""
    return f"A concise technical briefing about {text}."


def _case(
    name: str,
    query: str,
    high: list[str],
    medium: list[str],
    synonyms: dict[str, list[str]],
    candidates: tuple[CandidateCase, ...],
) -> EvaluationCase:
    # Every fixture deliberately has ten positives and two body-only negatives.
    # This makes the expected metric record stable while the candidate ordering
    # still exercises title, synonym, lead, and duplicate paths.
    assert len(candidates) == 12
    assert sum(candidate.expected_relevant for candidate in candidates) == 10
    return EvaluationCase(
        name=name,
        query=query,
        initial_keywords={"high": high, "medium": medium},
        topic_synonyms=synonyms,
        candidates=candidates,
        # Python-safe names for precision@5 and precision@10 are used here.
        expected_metrics={
            "precision_at_5": 1.0,
            "precision_at_10": 1.0,
            "recall": 1.0,
            "ndcg": 1.0,
            "mrr": 1.0,
            "false_positive_rate": 0.0,
            "coverage": 10 / 12,
            "abstention": 2 / 12,
        },
    )


EVALUATION_CASES = (
    _case(
        "security-engineer",
        "Kubernetes security vulnerabilities and supply-chain hardening",
        ["kubernetes", "security", "cve"],
        ["supply chain", "hardening"],
        {
            "kubernetes": ["k8s", "kubectl", "helm"],
            "security": ["infosec", "cybersecurity", "appsec"],
        },
        (
            CandidateCase(
                "https://fixture.test/security/1",
                "Kubernetes admission control closes a critical CVE",
                "The patch hardens cluster workloads.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/security/wired",
                "Wired's guide to the best new TV shows",
                _body_only("Kubernetes security and CVE coverage appear in a sidebar."),
                False,
            ),
            CandidateCase(
                "https://fixture.test/security/2",
                "K8s hardening checklist for production clusters",
                "Apply these controls before the next deploy.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/security/3",
                "Critical Kubernetes CVE affects admission controllers",
                "A second source covers the same vulnerability.",
                True,
                duplicate_of="https://fixture.test/security/1",
            ),
            CandidateCase(
                "https://fixture.test/security/4",
                "Cluster policy update for safer deployments",
                _lead("security and supply chain controls"),
                True,
            ),
            CandidateCase(
                "https://fixture.test/security/5",
                "AppSec teams coordinate a new vulnerability disclosure",
                "The disclosure includes remediation guidance.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/security/noise",
                "Wired reviews a streaming television finale",
                _body_only("The article later mentions cybersecurity and Kubernetes."),
                False,
            ),
            CandidateCase(
                "https://fixture.test/security/6",
                "Kubectl and Helm updates improve Kubernetes operations",
                "Release notes include security fixes.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/security/7",
                "Security engineers share supply-chain hardening lessons",
                "Teams compare practical controls.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/security/8",
                "Cybersecurity response tracks another Kubernetes CVE",
                "The incident report is now public.",
                True,
                duplicate_of="https://fixture.test/security/3",
            ),
            CandidateCase(
                "https://fixture.test/security/9",
                "Kubernetes security release protects worker nodes",
                "Upgrade guidance is available.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/security/10",
                "AppSec review finds a supply-chain weakness",
                "The fix is ready for maintainers.",
                True,
            ),
        ),
    ),
    _case(
        "developer-infra",
        "Platform engineering, Kubernetes, Terraform, CI/CD, and observability",
        ["kubernetes", "terraform", "platform", "observability"],
        ["ci/cd", "infrastructure"],
        {
            "kubernetes": ["k8s", "helm"],
            "observability": ["telemetry", "tracing", "opentelemetry"],
        },
        (
            CandidateCase(
                "https://fixture.test/infra/1",
                "Platform teams standardize Terraform modules",
                "The modules reduce drift across environments.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/infra/wired",
                "Wired's TV round-up for the weekend",
                _body_only("Terraform and observability show up in unrelated article links."),
                False,
            ),
            CandidateCase(
                "https://fixture.test/infra/2",
                "K8s deployment patterns for reliable CI/CD",
                "A practical guide for developer infrastructure.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/infra/3",
                "Terraform platform automation reaches production",
                "This follows the same rollout as another provider.",
                True,
                duplicate_of="https://fixture.test/infra/1",
            ),
            CandidateCase(
                "https://fixture.test/infra/4",
                "A neutral engineering update",
                _lead("observability and infrastructure migration"),
                True,
            ),
            CandidateCase(
                "https://fixture.test/infra/5",
                "OpenTelemetry tracing cuts service debugging time",
                "Telemetry is correlated across services.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/infra/noise",
                "A critic ranks this season's television shows",
                _body_only("The page mentions platform engineering and Kubernetes in its footer."),
                False,
            ),
            CandidateCase(
                "https://fixture.test/infra/6",
                "CI/CD infrastructure gets safer rollout controls",
                "Deployment teams can pause unhealthy releases.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/infra/7",
                "Platform engineering handbook adds service ownership",
                "The handbook covers internal developer tooling.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/infra/8",
                "Helm and Kubernetes operators simplify cluster upgrades",
                "The operator has a compatible migration path.",
                True,
                duplicate_of="https://fixture.test/infra/2",
            ),
            CandidateCase(
                "https://fixture.test/infra/9",
                "Observability teams adopt distributed tracing",
                "The dashboards expose latency regressions.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/infra/10",
                "Terraform infrastructure review catches configuration drift",
                "The review closes an operational gap.",
                True,
            ),
        ),
    ),
    _case(
        "ai-researcher-qwen",
        "Qwen3.8 release notes, open models, benchmarks, and inference",
        ["qwen", "release", "model", "inference"],
        ["benchmark", "open weights"],
        {
            "qwen": ["alibaba", "qwen3"],
            "inference": ["serving", "vllm"],
        },
        (
            CandidateCase(
                "https://fixture.test/qwen/1",
                "Qwen3.8 release improves open-model inference",
                "Researchers measure faster serving on common GPUs.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/qwen/wired",
                "Wired's review of a new television season",
                _body_only("Qwen benchmarks and model inference are mentioned in references."),
                False,
            ),
            CandidateCase(
                "https://fixture.test/qwen/2",
                "Alibaba announces a Qwen3 model checkpoint",
                "The checkpoint includes evaluation scripts.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/qwen/3",
                "Qwen release benchmark compares open weights",
                "A second lab reports the same release.",
                True,
                duplicate_of="https://fixture.test/qwen/1",
            ),
            CandidateCase(
                "https://fixture.test/qwen/4",
                "A new lab report lands today",
                _lead("Qwen inference serving and benchmark results"),
                True,
            ),
            CandidateCase(
                "https://fixture.test/qwen/5",
                "vLLM serving update targets Qwen workloads",
                "The inference engine adds memory improvements.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/qwen/noise",
                "TV makers reveal their autumn lineup",
                _body_only("The article's bibliography includes Qwen release notes."),
                False,
            ),
            CandidateCase(
                "https://fixture.test/qwen/6",
                "Open model researchers reproduce Qwen benchmarks",
                "The results include model cards and code.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/qwen/7",
                "Qwen3 inference evaluation reveals a latency tradeoff",
                "The tradeoff depends on quantization.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/qwen/8",
                "Alibaba Qwen release adds a longer context window",
                "The release is available under open weights.",
                True,
                duplicate_of="https://fixture.test/qwen/3",
            ),
            CandidateCase(
                "https://fixture.test/qwen/9",
                "Model serving researchers tune inference kernels",
                "The experiment includes Qwen workloads.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/qwen/10",
                "Qwen benchmark suite adds multilingual tasks",
                "Researchers publish reproducible measurements.",
                True,
            ),
        ),
    ),
    _case(
        "fpv-drone",
        "FPV drone flight controllers, Betaflight, and digital video",
        ["fpv", "drone", "betaflight", "flight controller"],
        ["digital video", "quad"],
        {
            "drone": ["uav", "quadcopter"],
            "digital video": ["hdzero", "walksnail"],
        },
        (
            CandidateCase(
                "https://fixture.test/fpv/1",
                "Betaflight tunes an FPV flight controller",
                "The release improves blackbox logging.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/fpv/wired",
                "Wired's list of the year's television shows",
                _body_only("Drone video and FPV tuning appear only in the article's tags."),
                False,
            ),
            CandidateCase(
                "https://fixture.test/fpv/2",
                "UAV builders test a new digital video link",
                "The link improves range for pilots.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/fpv/3",
                "FPV drone pilots compare the latest video system",
                "A second review covers the same launch.",
                True,
                duplicate_of="https://fixture.test/fpv/2",
            ),
            CandidateCase(
                "https://fixture.test/fpv/4",
                "A new quad build ships this week",
                _lead("flight controller and Betaflight configuration"),
                True,
            ),
            CandidateCase(
                "https://fixture.test/fpv/5",
                "HDZero digital video update lowers latency",
                "Pilots report a clearer link.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/fpv/noise",
                "The best television finales to stream tonight",
                _body_only("FPV drone footage is cited in a late photo caption."),
                False,
            ),
            CandidateCase(
                "https://fixture.test/fpv/6",
                "Quads get safer Betaflight failsafe defaults",
                "The defaults are documented for new builders.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/fpv/7",
                "FPV pilots migrate to a digital video receiver",
                "A field test compares antennas.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/fpv/8",
                "Walksnail video hardware fits compact FPV drones",
                "The hardware is compatible with several frames.",
                True,
                duplicate_of="https://fixture.test/fpv/3",
            ),
            CandidateCase(
                "https://fixture.test/fpv/9",
                "Flight controller firmware adds drone telemetry",
                "Telemetry is visible in the goggles.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/fpv/10",
                "Betaflight release fixes a controller safety issue",
                "Builders should update before flying.",
                True,
            ),
        ),
    ),
    _case(
        "general-tech-consumer",
        "Useful consumer technology: phones, laptops, privacy, and batteries",
        ["phone", "laptop", "privacy", "battery"],
        ["technology", "device"],
        {
            "phone": ["smartphone", "mobile"],
            "laptop": ["notebook", "ultrabook"],
        },
        (
            CandidateCase(
                "https://fixture.test/consumer/1",
                "New phone privacy controls are easier to understand",
                "The settings explain which apps can access sensors.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/consumer/wired",
                "Wired picks ten television shows worth streaming",
                _body_only("Phone battery and laptop privacy tips are linked at the bottom."),
                False,
            ),
            CandidateCase(
                "https://fixture.test/consumer/2",
                "Smartphone battery test finds a clear winner",
                "The test covers everyday charging habits.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/consumer/3",
                "Laptop privacy review compares two new devices",
                "Another publication reports the same launch.",
                True,
                duplicate_of="https://fixture.test/consumer/1",
            ),
            CandidateCase(
                "https://fixture.test/consumer/4",
                "A practical device buying guide appears today",
                _lead("laptop battery life and privacy settings"),
                True,
            ),
            CandidateCase(
                "https://fixture.test/consumer/5",
                "Ultrabook makers improve battery repairability",
                "The design makes replacement less wasteful.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/consumer/noise",
                "Streaming television recommendations for a rainy day",
                _body_only("Smartphone privacy and battery are mentioned in the credits."),
                False,
            ),
            CandidateCase(
                "https://fixture.test/consumer/6",
                "Mobile device update adds a privacy dashboard",
                "The dashboard makes permissions visible.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/consumer/7",
                "Laptop buyers compare ports, displays, and battery life",
                "The comparison includes repair scores.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/consumer/8",
                "Phone privacy update ships after a security review",
                "The update is available to existing owners.",
                True,
                duplicate_of="https://fixture.test/consumer/6",
            ),
            CandidateCase(
                "https://fixture.test/consumer/9",
                "Consumer technology guide explains device longevity",
                "The guide includes batteries and repairability.",
                True,
            ),
            CandidateCase(
                "https://fixture.test/consumer/10",
                "New laptop device uses less battery power",
                "The manufacturer publishes measured results.",
                True,
            ),
        ),
    ),
)


def _precision(labels: list[bool], limit: int) -> float:
    return sum(labels[:limit]) / limit


def _recall(labels: list[bool], gold: list[bool]) -> float:
    relevant = sum(gold)
    return sum(labels) / relevant if relevant else 1.0


def _ndcg(labels: list[bool], limit: int | None = None) -> float:
    observed = labels if limit is None else labels[:limit]
    dcg = sum((1.0 / log2(index + 2)) for index, label in enumerate(observed) if label)
    ideal_count = min(sum(labels), len(observed))
    ideal = sum(1.0 / log2(index + 2) for index in range(ideal_count))
    return dcg / ideal if ideal else 1.0


def _mrr(labels: list[bool]) -> float:
    return next(
        (1.0 / (index + 1) for index, label in enumerate(labels) if label),
        0.0,
    )


@pytest.mark.parametrize("case", EVALUATION_CASES, ids=lambda case: case.name)
def test_relevance_gate_labels_realistic_profiles(case: EvaluationCase) -> None:
    """The gate accepts title/lead intent but rejects incidental body hits."""
    predictions: list[bool] = []
    eligible_urls: list[str] = []
    evidence_by_url: dict[str, dict[str, Any]] = {}

    for candidate in case.candidates:
        eligible, evidence = evaluate_relevance(
            candidate.as_article(),
            case.initial_keywords,
            case.topic_synonyms,
        )
        predictions.append(eligible)
        evidence_by_url[candidate.url] = evidence
        if eligible:
            eligible_urls.append(candidate.url)
        assert eligible is candidate.expected_relevant, (
            case.name,
            candidate.url,
            evidence,
        )

    expected_urls = [
        candidate.url for candidate in case.candidates if candidate.expected_relevant
    ]
    assert eligible_urls == expected_urls

    for candidate in case.candidates:
        evidence = evidence_by_url[candidate.url]
        assert set(evidence) >= {
            "matched_terms",
            "title_matches",
            "context_matches",
            "relevance_reason",
            "selected",
        }
        assert evidence["selected"] is False
        if candidate.expected_relevant:
            assert evidence["title_matches"] or evidence["context_matches"]
        else:
            assert evidence["title_matches"] == []
            assert evidence["context_matches"] == []
            assert evidence["relevance_reason"] == "no_title_or_lead_keyword"

    # Near-duplicates are independently relevant here; deduplication is a
    # later ranking stage and must not hide evidence from this evaluation.
    for candidate in case.candidates:
        if candidate.duplicate_of:
            assert candidate.url in eligible_urls
            assert candidate.duplicate_of in eligible_urls


def test_relevance_metrics_are_recorded_for_each_profile() -> None:
    """Compute the metric record attached to every fixture, offline."""
    for case in EVALUATION_CASES:
        gold = [candidate.expected_relevant for candidate in case.candidates]
        predicted = [
            evaluate_relevance(
                candidate.as_article(),
                case.initial_keywords,
                case.topic_synonyms,
            )[0]
            for candidate in case.candidates
        ]
        accepted = [
            expected
            for expected, is_eligible in zip(gold, predicted)
            if is_eligible
        ]
        false_positives = sum(
            is_eligible and not expected
            for expected, is_eligible in zip(gold, predicted)
        )
        negatives = len(gold) - sum(gold)
        metrics = {
            "precision_at_5": _precision(accepted, 5),
            "precision_at_10": _precision(accepted, 10),
            "recall": _recall(accepted, gold),
            "ndcg": _ndcg(accepted),
            "mrr": _mrr(accepted),
            "false_positive_rate": false_positives / negatives,
            "coverage": sum(predicted) / len(predicted),
            "abstention": sum(not value for value in predicted) / len(predicted),
        }
        assert metrics == pytest.approx(case.expected_metrics)


def test_candidate_serialization_is_bounded_and_reasoning_free() -> None:
    article = {
        "url": "https://fixture.test/safe",
        "title": "Kubernetes security patch",
        "source": "Fixture source",
        "category": "Security",
        "published_at": "2026-08-08T10:00:00+00:00",
        "content": "Visible lead. " + ("private body " * 200),
        "preference_score": 4.5,
        "score_breakdown": {
            "keyword_high": 2.0,
            "term_overlap": 1.5,
            "llm_rerank": 0.2,
            "llm_reason": "raw provider reasoning must not escape",
        },
    }
    eligible, evidence = evaluate_relevance(
        article,
        {"high": ["kubernetes", "security"], "medium": []},
    )
    assert eligible is True

    candidate = serialize_candidate(
        article,
        rank=3,
        selected=True,
        evidence=evidence,
        excerpt_chars=40,
    )
    assert candidate["rank"] == 3
    assert candidate["evidence"]["selected"] is True
    assert len(candidate["excerpt"]) <= 41  # bounded text may include an ellipsis
    assert "content" not in candidate
    assert "llm_reason" not in candidate["score_breakdown"]
    assert all(
        isinstance(value, (int, float))
        for value in candidate["score_breakdown"].values()
    )


def test_no_configured_intent_is_open_discovery() -> None:
    """General discovery remains open when no profile keywords are configured."""
    eligible, evidence = evaluate_relevance(
        {
            "url": "https://fixture.test/general",
            "title": "A story without a configured topic",
            "content": "The article is still useful for general discovery.",
        },
        {"high": [], "medium": []},
    )
    assert eligible is True
    assert evidence["relevance_reason"] == "no_configured_keywords"
    assert evidence["matched_terms"] == []
    assert evidence["selected"] is False
