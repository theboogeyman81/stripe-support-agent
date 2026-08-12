"""Tests for src/eval/judge.py — all external clients mocked."""

from unittest.mock import MagicMock

from src.eval.judge import extract_tool_calls, score_tone, score_tool_choice


def _mock_client(json_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value.text = json_text
    return client


# ── extract_tool_calls ───────────────────────────────────────────────────────


def test_extract_tool_calls_returns_names() -> None:
    """Tool-call parts yield tool names in order."""
    history = [
        {"parts": [{"part_kind": "tool-call", "tool_name": "search_docs"}]},
        {"parts": [{"part_kind": "tool-call", "tool_name": "calculate"}]},
    ]
    assert extract_tool_calls(history) == ["search_docs", "calculate"]


def test_extract_tool_calls_empty_when_no_tool_calls() -> None:
    """History with only text parts returns empty list."""
    history = [{"parts": [{"part_kind": "text", "content": "hello"}]}]
    assert extract_tool_calls(history) == []


def test_extract_tool_calls_ignores_non_tool_call_parts() -> None:
    """Text and tool-return parts are ignored; only tool-call parts counted."""
    history = [
        {
            "parts": [
                {"part_kind": "text", "content": "I'll look that up."},
                {"part_kind": "tool-call", "tool_name": "lookup_user"},
                {"part_kind": "tool-return", "tool_name": "lookup_user"},
            ]
        }
    ]
    assert extract_tool_calls(history) == ["lookup_user"]


# ── score_tool_choice ────────────────────────────────────────────────────────


def test_score_tool_choice_returns_score_and_rationale() -> None:
    """Valid JSON response is parsed into score and rationale."""
    client = _mock_client('{"score": 1.0, "rationale": "Correct tool called."}')
    result = score_tool_choice(
        "What is a PaymentIntent?", ["search_docs"], "...", client, "test-model"
    )
    assert result["score"] == 1.0
    assert result["rationale"] == "Correct tool called."


def test_score_tool_choice_handles_parse_error() -> None:
    """Unparseable JSON returns neutral score and parse-error rationale."""
    client = _mock_client("not json at all")
    result = score_tool_choice(
        "What is a PaymentIntent?", [], "...", client, "test-model"
    )
    assert result["score"] == 0.5
    assert result["rationale"] == "parse error"


# ── score_tone ───────────────────────────────────────────────────────────────


def test_score_tone_returns_score_and_rationale() -> None:
    """Valid JSON response is parsed into score and rationale."""
    client = _mock_client('{"score": 0.5, "rationale": "Slightly too long."}')
    result = score_tone(
        "What is a PaymentIntent?", "A PaymentIntent is...", client, "test-model"
    )
    assert result["score"] == 0.5
    assert result["rationale"] == "Slightly too long."


def test_score_tone_handles_parse_error() -> None:
    """Unparseable JSON returns neutral score and parse-error rationale."""
    client = _mock_client("```json\n{broken}")
    result = score_tone(
        "What is a PaymentIntent?", "...", client, "test-model"
    )
    assert result["score"] == 0.5
    assert result["rationale"] == "parse error"
