"""Tests for src/agent/tools.py — retrieve() mocked, no network calls."""

import pytest
from unittest.mock import patch, MagicMock

from src.agent.tools import calculate, create_ticket, lookup_user, search_docs

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
    ctx = MagicMock()
    ctx.deps.langfuse_public_key = ""
    ctx.deps.langfuse_secret_key = ""
    return ctx


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


# --- calculate tests ---


def test_calculate_addition():
    assert calculate(_ctx(), "2 + 3") == "5"


def test_calculate_float_result():
    assert calculate(_ctx(), "10 / 4") == "2.5"


def test_calculate_stripe_fee():
    assert calculate(_ctx(), "(120 * 0.029) + 0.30") == "3.78"


def test_calculate_large_multiply():
    assert calculate(_ctx(), "12000 * 0.035") == "420"


def test_calculate_power():
    assert calculate(_ctx(), "2 ** 8") == "256"


def test_calculate_unary_minus():
    assert calculate(_ctx(), "-5 + 10") == "5"


def test_calculate_empty_raises():
    with pytest.raises(ValueError, match="expression must not be empty"):
        calculate(_ctx(), "")


def test_calculate_whitespace_raises():
    with pytest.raises(ValueError, match="expression must not be empty"):
        calculate(_ctx(), "   ")


def test_calculate_disallowed_name_raises():
    with pytest.raises(ValueError, match="disallowed expression"):
        calculate(_ctx(), "x + 1")


def test_calculate_disallowed_call_raises():
    with pytest.raises(ValueError, match="disallowed expression"):
        calculate(_ctx(), "abs(-1)")


def test_calculate_division_by_zero_raises():
    with pytest.raises(ValueError, match="division by zero"):
        calculate(_ctx(), "1 / 0")


def test_calculate_invalid_syntax_raises():
    with pytest.raises(ValueError, match="invalid expression"):
        calculate(_ctx(), "2 +")


# --- create_ticket tests ---


def _ctx_with_postgres() -> MagicMock:
    ctx = MagicMock()
    ctx.deps.postgres_url = "postgresql://fake/db"
    ctx.deps.langfuse_public_key = ""
    ctx.deps.langfuse_secret_key = ""
    return ctx


def _ctx_no_postgres() -> MagicMock:
    ctx = MagicMock()
    ctx.deps.postgres_url = ""
    ctx.deps.langfuse_public_key = ""
    ctx.deps.langfuse_secret_key = ""
    return ctx


def test_create_ticket_returns_confirmation():
    with patch("src.agent.tools.insert_ticket", return_value=1):
        result = create_ticket(_ctx_with_postgres(), "billing", "I was double-charged")
    assert result == "Ticket #1 created (category: billing)."


def test_create_ticket_empty_url_raises():
    with pytest.raises(ValueError, match="postgres_url is not configured"):
        create_ticket(_ctx_no_postgres(), "billing", "Test")


def test_create_ticket_passes_args_to_insert():
    with patch("src.agent.tools.insert_ticket", return_value=5) as mock_insert:
        create_ticket(_ctx_with_postgres(), "billing", "I was double-charged")
    mock_insert.assert_called_once_with(
        "postgresql://fake/db", "billing", "I was double-charged"
    )


# --- lookup_user tests ---

_ALICE = {
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "plan": "Starter",
    "status": "active",
}

_CAROL = {
    "name": "Carol Chen",
    "email": "carol@example.com",
    "plan": "Enterprise",
    "status": "suspended",
}


def _ctx_plain() -> MagicMock:
    ctx = MagicMock()
    ctx.deps.langfuse_public_key = ""
    ctx.deps.langfuse_secret_key = ""
    return ctx


def test_lookup_user_found():
    with patch("src.agent.tools.MOCK_USERS", {"alice@example.com": _ALICE}):
        result = lookup_user(_ctx_plain(), "alice@example.com")
    assert "Alice Johnson" in result
    assert "Starter" in result
    assert "active" in result


def test_lookup_user_not_found():
    with patch("src.agent.tools.MOCK_USERS", {}):
        result = lookup_user(_ctx_plain(), "unknown@example.com")
    assert result == "No user found for email: unknown@example.com."


def test_lookup_user_case_insensitive():
    with patch("src.agent.tools.MOCK_USERS", {"alice@example.com": _ALICE}):
        result = lookup_user(_ctx_plain(), "ALICE@EXAMPLE.COM")
    assert "Alice Johnson" in result


def test_lookup_user_empty_raises():
    with pytest.raises(ValueError, match="email must not be empty"):
        lookup_user(_ctx_plain(), "")


def test_lookup_user_whitespace_raises():
    with pytest.raises(ValueError, match="email must not be empty"):
        lookup_user(_ctx_plain(), "   ")


def test_lookup_user_suspended_status():
    with patch("src.agent.tools.MOCK_USERS", {"carol@example.com": _CAROL}):
        result = lookup_user(_ctx_plain(), "carol@example.com")
    assert "suspended" in result


# --- tracing tests ---


def test_search_docs_creates_span():
    mock_client = MagicMock()
    mock_span = MagicMock()
    mock_client.start_observation.return_value = mock_span
    with patch("src.agent.tools.get_langfuse_client", return_value=mock_client), \
         patch("src.agent.tools.retrieve", return_value=[]):
        search_docs(_ctx(), "PaymentIntent")
    mock_client.start_observation.assert_called_once_with(
        name="search_docs", as_type="span", input={"query": "PaymentIntent"}
    )
    mock_span.end.assert_called_once()


def test_calculate_creates_span():
    mock_client = MagicMock()
    mock_span = MagicMock()
    mock_client.start_observation.return_value = mock_span
    with patch("src.agent.tools.get_langfuse_client", return_value=mock_client):
        calculate(_ctx(), "2 + 3")
    mock_client.start_observation.assert_called_once_with(
        name="calculate", as_type="span", input={"expression": "2 + 3"}
    )
    mock_span.end.assert_called_once()


def test_create_ticket_creates_span():
    mock_client = MagicMock()
    mock_span = MagicMock()
    mock_client.start_observation.return_value = mock_span
    with patch("src.agent.tools.get_langfuse_client", return_value=mock_client), \
         patch("src.agent.tools.insert_ticket", return_value=1):
        create_ticket(_ctx_with_postgres(), "billing", "double charge")
    mock_client.start_observation.assert_called_once_with(
        name="create_ticket", as_type="span",
        input={"category": "billing", "summary": "double charge"}
    )
    mock_span.end.assert_called_once()


def test_lookup_user_creates_span():
    mock_client = MagicMock()
    mock_span = MagicMock()
    mock_client.start_observation.return_value = mock_span
    with patch("src.agent.tools.get_langfuse_client", return_value=mock_client), \
         patch("src.agent.tools.MOCK_USERS", {}):
        lookup_user(_ctx_plain(), "test@example.com")
    mock_client.start_observation.assert_called_once_with(
        name="lookup_user", as_type="span", input={"email": "test@example.com"}
    )
    mock_span.end.assert_called_once()


def test_search_docs_skips_span_when_client_absent():
    with patch("src.agent.tools.get_langfuse_client", return_value=None), \
         patch("src.agent.tools.retrieve", return_value=[]):
        result = search_docs(_ctx(), "PaymentIntent")
    assert result == "No relevant documentation found."
