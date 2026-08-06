"""Tests for src/agent/agent.py — all external calls mocked via Agent('test')."""

import pytest
from unittest.mock import patch
from pydantic_ai import Agent

from src.agent.agent import SYSTEM_PROMPT, create_agent, run_agent
from src.config import Settings


def _settings() -> Settings:
    return Settings(
        gemini_api_key="test-key",
        voyage_api_key="test-key",
        qdrant_url="http://localhost:6333",
    )


def _test_agent() -> Agent:
    return Agent("test", system_prompt="test")


def test_create_agent_returns_agent_instance():
    agent = create_agent(_settings())
    assert isinstance(agent, Agent)


def test_run_agent_returns_all_keys():
    with patch("src.agent.agent.create_agent", return_value=_test_agent()):
        result = run_agent("What is a PaymentIntent?", _settings())
    assert set(result.keys()) == {"answer", "input_tokens", "output_tokens", "cost_usd", "message_history"}


def test_run_agent_answer_is_string():
    with patch("src.agent.agent.create_agent", return_value=_test_agent()):
        result = run_agent("What is a PaymentIntent?", _settings())
    assert isinstance(result["answer"], str)


def test_run_agent_cost_is_non_negative():
    with patch("src.agent.agent.create_agent", return_value=_test_agent()):
        result = run_agent("What is a PaymentIntent?", _settings())
    assert result["cost_usd"] >= 0


def test_run_agent_empty_question_raises():
    with pytest.raises(ValueError, match="question must not be empty"):
        run_agent("", _settings())


def test_run_agent_whitespace_only_raises():
    with pytest.raises(ValueError, match="question must not be empty"):
        run_agent("   ", _settings())


def test_system_prompt_mentions_search_docs():
    assert "search_docs" in SYSTEM_PROMPT


def test_system_prompt_mentions_create_ticket():
    assert "create_ticket" in SYSTEM_PROMPT


def test_system_prompt_mentions_lookup_user():
    assert "lookup_user" in SYSTEM_PROMPT


def test_system_prompt_mentions_calculate():
    assert "calculate" in SYSTEM_PROMPT


def test_run_agent_returns_message_history_key():
    with patch("src.agent.agent.create_agent", return_value=_test_agent()):
        result = run_agent("hello", _settings())
    assert "message_history" in result
    assert isinstance(result["message_history"], list)


def test_run_agent_history_grows_on_second_turn():
    with patch("src.agent.agent.create_agent", return_value=_test_agent()):
        r1 = run_agent("hello", _settings())
        r2 = run_agent("follow up", _settings(), message_history=r1["message_history"])
    assert len(r2["message_history"]) > len(r1["message_history"])


def test_run_agent_none_history_still_works():
    with patch("src.agent.agent.create_agent", return_value=_test_agent()):
        result = run_agent("hello", _settings(), message_history=None)
    assert "message_history" in result
