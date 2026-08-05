"""Tests for src/db/tickets.py — psycopg.connect mocked, no network calls."""

from unittest.mock import MagicMock, call, patch

from src.db.tickets import ensure_tickets_table, insert_ticket

_FAKE_URL = "postgresql://fake:fake@localhost/testdb"


def _make_conn_mock(returning_id: int = 1) -> MagicMock:
    """Return a mock that behaves like a psycopg connection context manager."""
    row = (returning_id,)
    cursor_mock = MagicMock()
    cursor_mock.fetchone.return_value = row
    conn_mock = MagicMock()
    conn_mock.execute.return_value = cursor_mock
    conn_mock.__enter__ = lambda s: s
    conn_mock.__exit__ = MagicMock(return_value=False)
    return conn_mock


def test_ensure_tickets_table_executes_create():
    conn_mock = _make_conn_mock()
    with patch("src.db.tickets.psycopg.connect", return_value=conn_mock):
        ensure_tickets_table(_FAKE_URL)
    sql_called = conn_mock.execute.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS tickets" in sql_called


def test_ensure_tickets_table_commits():
    conn_mock = _make_conn_mock()
    with patch("src.db.tickets.psycopg.connect", return_value=conn_mock):
        ensure_tickets_table(_FAKE_URL)
    conn_mock.commit.assert_called_once()


def test_insert_ticket_returns_id():
    conn_mock = _make_conn_mock(returning_id=42)
    with patch("src.db.tickets.psycopg.connect", return_value=conn_mock), \
         patch("src.db.tickets.ensure_tickets_table"):
        result = insert_ticket(_FAKE_URL, "billing", "Double charge")
    assert result == 42


def test_insert_ticket_calls_ensure_first():
    conn_mock = _make_conn_mock()
    with patch("src.db.tickets.psycopg.connect", return_value=conn_mock), \
         patch("src.db.tickets.ensure_tickets_table") as mock_ensure:
        insert_ticket(_FAKE_URL, "billing", "Test")
    mock_ensure.assert_called_once_with(_FAKE_URL)


def test_insert_ticket_uses_parameterised_query():
    conn_mock = _make_conn_mock()
    with patch("src.db.tickets.psycopg.connect", return_value=conn_mock), \
         patch("src.db.tickets.ensure_tickets_table"):
        insert_ticket(_FAKE_URL, "account", "Can't log in")
    sql, params = conn_mock.execute.call_args[0]
    assert "%s" in sql
    assert params == ("account", "Can't log in")
