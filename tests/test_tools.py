"""Tests for src/agent/tools.py — retrieve() mocked, no network calls."""

import pytest
from unittest.mock import patch, MagicMock
from pydantic_ai import RunContext

from src.agent.tools import search_docs

_CHUNK = {
    "doc_title": "PaymentIntents",
    "doc_url": "https://stripe.com/docs/api/payment_intents",
    "text": "A PaymentIntent guides you through the process of collecting a payment.",
}

_CHUNK_2 = {
    "doc_title": "Charges",
    "doc_url": "https://stripe.com/docs/api/charges",
    "text": "A Charge represents a charge on a credit or debit card.",
}


def _ctx() -> MagicMock:
    return MagicMock(spec=RunContext)


def test_search_docs_formats_single_chunk():
    with patch("src.agent.tools.retrieve", return_value=[_CHUNK]):
        result = search_docs(_ctx(), "PaymentIntent")
    assert "[1] PaymentIntents" in result
    assert "https://stripe.com/docs/api/payment_intents" in result
    assert "A PaymentIntent guides" in result


def test_search_docs_empty_results():
    with patch("src.agent.tools.retrieve", return_value=[]):
        result = search_docs(_ctx(), "something obscure")
    assert result == "No relevant documentation found."


def test_search_docs_multiple_chunks():
    with patch("src.agent.tools.retrieve", return_value=[_CHUNK, _CHUNK_2]):
        result = search_docs(_ctx(), "payments")
    assert "[1] PaymentIntents" in result
    assert "[2] Charges" in result


def test_search_docs_empty_query_raises():
    with pytest.raises(ValueError, match="query must not be empty"):
        search_docs(_ctx(), "")


def test_search_docs_whitespace_query_raises():
    with pytest.raises(ValueError, match="query must not be empty"):
        search_docs(_ctx(), "   ")
