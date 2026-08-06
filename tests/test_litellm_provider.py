"""Tests for the unified LiteLLM model backend and reasoning controls."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from condenseit.providers.base import (
    CHAT_SYSTEM_PROMPT,
    build_chat_user_prompt,
    parse_summary_response,
)
from condenseit.providers.litellm_client import call_litellm
from condenseit.providers.litellm_provider import LiteLLMSummarizer


def _install_fake_litellm(monkeypatch, response):
    calls: list[dict] = []

    def completion(**kwargs):
        calls.append(kwargs)
        return response

    fake = SimpleNamespace(completion=completion)
    monkeypatch.setitem(sys.modules, "litellm", fake)
    return calls


def test_litellm_call_qualifies_provider_and_forwards_reasoning(monkeypatch) -> None:
    response = {
        "choices": [{"message": {"content": "answer"}}],
        "usage": {"total_tokens": 23, "cost": 0.0042},
    }
    calls = _install_fake_litellm(monkeypatch, response)
    budget = MagicMock()

    result = call_litellm(
        provider="custom",
        model="local-model",
        messages=[{"role": "user", "content": "hello"}],
        api_key="sk-test",
        base_url="http://localhost:8000/v1/",
        reasoning_effort="high",
        thinking_enabled=True,
        thinking_budget_tokens=4096,
        extra_headers={"X-Test": "yes"},
        budget=budget,
    )

    assert result.content == "answer"
    assert result.total_tokens == 23
    assert result.cost_usd == 0.0042
    assert calls[0]["model"] == "openai/local-model"
    assert calls[0]["api_base"] == "http://localhost:8000/v1"
    assert calls[0]["reasoning_effort"] == "high"
    assert calls[0]["extra_body"] == {
        "thinking": {"type": "enabled", "budget_tokens": 4096}
    }
    assert calls[0]["extra_headers"] == {"X-Test": "yes"}
    budget.record_spend.assert_called_once_with(
        0.0042,
        model="local-model",
        tokens=23,
    )

def test_litellm_call_stops_before_request_when_budget_is_exhausted(
    monkeypatch,
) -> None:
    calls = _install_fake_litellm(
        monkeypatch,
        {"choices": [{"message": {"content": "should not be used"}}]},
    )
    budget = MagicMock()
    budget.can_spend.return_value = False

    try:
        call_litellm(
            provider="openrouter",
            model="qwen/model",
            messages=[{"role": "user", "content": "hello"}],
            budget=budget,
        )
    except RuntimeError as exc:
        assert str(exc) == "OpenRouter daily or monthly budget exceeded"
    else:
        raise AssertionError("Expected exhausted budget to stop the request")

    assert calls == []


def test_litellm_call_drops_reasoning_blocks_from_mixed_content(monkeypatch) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "private"},
                        {"type": "text", "text": "visible"},
                    ]
                }
            }
        ]
    }
    _install_fake_litellm(monkeypatch, response)

    result = call_litellm(
        provider="openrouter",
        model="qwen/model",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert result.content == "visible"

def test_litellm_call_ignores_nested_reasoning_fields(monkeypatch) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "visible one"},
                        {
                            "type": "text",
                            "content": [
                                {"type": "thinking", "thinking": "private nested"},
                                {"type": "text", "text": "visible two"},
                            ],
                        },
                        {"reasoning_content": [{"text": "private field"}]},
                    ],
                    "reasoning": "private top-level",
                    "reasoning_content": ["private top-level list"],
                    "thinking": {"content": "private nested field"},
                }
            }
        ]
    }
    _install_fake_litellm(monkeypatch, response)

    result = call_litellm(
        provider="openrouter",
        model="qwen/model",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert result.content == "visible one\nvisible two"


def test_parse_summary_response_strips_thinking_prefix_and_fields() -> None:
    payload = {
        "tldr": "<thinking>private field thought</thinking>Visible tldr",
        "key_takeaways": ["<analysis>private takeaway</analysis>Visible takeaway"],
        "summary": "Visible summary",
        "topics": ["visible topic"],
        "entities": [],
        "novelty": 4,
        "relevance_to_you": "Visible relevance",
    }

    result = parse_summary_response(
        "<think>private prefix thought</think>\n" + json.dumps(payload)
    )

    assert result["tldr"] == "Visible tldr"
    assert result["key_takeaways"] == ["Visible takeaway"]
    assert result["summary"] == "Visible summary"
    assert result["relevance_to_you"] == "Visible relevance"
    assert "private" not in json.dumps(result)


def test_parse_summary_response_discards_unclosed_thinking_prefix() -> None:
    result = parse_summary_response("<analysis>private unfinished thought")

    assert result["tldr"] == ""
    assert result["key_takeaways"] == []
    assert result["summary"] == ""
    assert result["topics"] == []
    assert result["entities"] == []
    assert result["novelty"] == 0
    assert result["relevance_to_you"] == ""

def test_parse_summary_response_discards_plain_thinking_transcript() -> None:
    raw = (
        "Thinking Process:\n\n"
        "1. **Analyze the Request:** draft a JSON response.\n"
        "2. **Refine and Validate:** check the required fields.\n"
        "I will output the final JSON next."
    )

    result = parse_summary_response(raw)

    assert result["tldr"] == ""
    assert result["key_takeaways"] == []
    assert result["summary"] == ""
    assert "thinking process" not in json.dumps(result).lower()



def test_parse_summary_response_recovers_visible_fields_from_malformed_json() -> None:
    raw = (
        '<reasoning>private prefix</reasoning>'
        '{"tldr":"Visible tldr","summary":"Visible summary","broken":'
    )

    result = parse_summary_response(raw)

    assert result["tldr"] == "Visible tldr"
    assert result["summary"] == "Visible summary"
    assert "private" not in json.dumps(result)

def test_parse_summary_response_recovers_payload_after_plain_thinking_prefix() -> None:
    raw = (
        "Thinking Process:\n"
        "1. Draft the answer and validate the requested schema.\n"
        "6. Constructing the JSON:\n"
        '```json\n{"tldr":"Visible tldr","summary":"Visible summary",\n'
    )

    result = parse_summary_response(raw)

    assert result["tldr"] == "Visible tldr"
    assert result["summary"] == "Visible summary"
    assert "thinking process" not in json.dumps(result).lower()

def test_parse_summary_response_discards_ellipsis_placeholder() -> None:
    result = parse_summary_response("...")

    assert result["tldr"] == ""
    assert result["key_takeaways"] == []
    assert result["summary"] == ""


def test_parse_summary_response_preserves_ordinary_angle_bracket_text() -> None:
    result = parse_summary_response(
        json.dumps(
            {
                "tldr": "Visible",
                "key_takeaways": [],
                "summary": "The article compares 2 < 3 and keeps <not-reasoning> text.",
                "topics": [],
                "entities": [],
                "novelty": 2,
            }
        )
    )

    assert result["summary"] == (
        "The article compares 2 < 3 and keeps <not-reasoning> text."
    )



def test_litellm_summarizer_uses_shared_json_prompt(monkeypatch) -> None:
    payload = {
        "tldr": "Short",
        "key_takeaways": ["One"],
        "summary": "Long",
        "topics": ["ai"],
        "entities": [],
        "novelty": 3,
    }
    calls = _install_fake_litellm(
        monkeypatch,
        {"choices": [{"message": {"content": json.dumps(payload)}}]},
    )
    summarizer = LiteLLMSummarizer(
        provider="openrouter",
        model="qwen/model",
        api_key="sk-test",
        reasoning_effort="medium",
    )

    result = summarizer.summarize_article(
        {"title": "Title", "content": "Article body"}
    )

    assert result["tldr"] == "Short"
    assert calls[0]["model"] == "openrouter/qwen/model"
    assert calls[0]["reasoning_effort"] == "medium"
    assert "Title" in calls[0]["messages"][1]["content"]

def test_shared_prompt_contract_remains_provider_neutral() -> None:
    assert "JSON" in CHAT_SYSTEM_PROMPT
    prompt = build_chat_user_prompt(
        "Title",
        "Content",
        max_key_takeaways=2,
        max_summary_paragraphs=1,
    )
    assert "Title" in prompt
    assert "Content" in prompt
    assert "<takeaway 2>" in prompt
    assert "<takeaway 3>" not in prompt
    assert "1 paragraph" in prompt
