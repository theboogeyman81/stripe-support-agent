"""Tests for src/db/costs.py — all psycopg calls mocked."""

from unittest.mock import MagicMock, patch

import psycopg

from src.db.costs import DEFAULT_MODEL, ensure_costs_table, insert_cost

_PG_URL = "postgresql://user:pass@localhost/db"


def _mock_conn() -> MagicMock:
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


# --- ensure_costs_table ---

def test_ensure_costs_table_executes_create_table() -> None:
    """ensure_costs_table calls execute() with CREATE TABLE IF NOT EXISTS."""
    conn = _mock_conn()
    with patch("src.db.costs.psycopg.connect", return_value=conn):
        ensure_costs_table(_PG_URL)
    sql = conn.execute.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS request_costs" in sql


def test_ensure_costs_table_no_ops_when_url_empty() -> None:
    """Empty postgres_url → psycopg.connect is never called."""
    with patch("src.db.costs.psycopg.connect") as mock_connect:
        ensure_costs_table("")
    mock_connect.assert_not_called()


# --- insert_cost ---

def test_insert_cost_executes_insert_sql() -> None:
    """insert_cost calls execute() with INSERT INTO request_costs."""
    conn = _mock_conn()
    with patch("src.db.costs.psycopg.connect", return_value=conn):
        insert_cost(_PG_URL, 100, 20, 0.001, False)
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO request_costs" in sql


def test_insert_cost_passes_correct_values() -> None:
    """insert_cost passes (input, output, cost, cache_hit, model) to execute."""
    conn = _mock_conn()
    with patch("src.db.costs.psycopg.connect", return_value=conn):
        insert_cost(_PG_URL, 100, 20, 0.001, False)
    params = conn.execute.call_args[0][1]
    assert params == (100, 20, 0.001, False, DEFAULT_MODEL)


def test_insert_cost_no_ops_when_url_empty() -> None:
    """Empty postgres_url → psycopg.connect is never called."""
    with patch("src.db.costs.psycopg.connect") as mock_connect:
        insert_cost("", 100, 20, 0.001, False)
    mock_connect.assert_not_called()


def test_insert_cost_swallows_psycopg_error() -> None:
    """A psycopg.Error during connect must not propagate to the caller."""
    with patch("src.db.costs.psycopg.connect", side_effect=psycopg.Error("down")):
        insert_cost(_PG_URL, 100, 20, 0.001, False)


def test_insert_cost_uses_default_model() -> None:
    """Omitting model kwarg → DEFAULT_MODEL is included in the execute tuple."""
    conn = _mock_conn()
    with patch("src.db.costs.psycopg.connect", return_value=conn):
        insert_cost(_PG_URL, 50, 10, 0.0005, True)
    params = conn.execute.call_args[0][1]
    assert params[4] == DEFAULT_MODEL
