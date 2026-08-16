"""Tests for the admin costs endpoint and query_costs() — all external I/O mocked."""

from unittest.mock import MagicMock, patch

import psycopg
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.db.costs import query_costs

_PG_URL = "postgresql://user:pass@localhost/db"

_ZERO = {
    "total_requests": 0,
    "cache_hits": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cost_usd": 0.0,
}
_SAMPLE = {
    "total_requests": 5,
    "cache_hits": 2,
    "total_input_tokens": 1000,
    "total_output_tokens": 200,
    "total_cost_usd": 0.005,
}


def _mock_conn() -> MagicMock:
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.admin_api_key = "changeme"
    mock.postgres_url = ""
    mock.redis_url = ""
    return mock


# --- query_costs unit tests ---

def test_query_costs_returns_correct_aggregates() -> None:
    """A mock row is parsed into the correct dict fields."""
    conn = _mock_conn()
    conn.execute.return_value.fetchone.return_value = (5, 2, 1000, 200, 0.005)
    with patch("src.db.costs.psycopg.connect", return_value=conn):
        result = query_costs(_PG_URL, 7)
    assert result["total_requests"] == 5
    assert result["cache_hits"] == 2
    assert result["total_input_tokens"] == 1000
    assert result["total_output_tokens"] == 200
    assert abs(result["total_cost_usd"] - 0.005) < 1e-9


def test_query_costs_returns_zeros_when_url_empty() -> None:
    """Empty postgres_url → zero dict, psycopg.connect never called."""
    with patch("src.db.costs.psycopg.connect") as mock_connect:
        result = query_costs("", 7)
    mock_connect.assert_not_called()
    assert result == _ZERO


def test_query_costs_returns_zeros_on_psycopg_error() -> None:
    """A psycopg.Error during connect → zero dict, no exception propagated."""
    with patch("src.db.costs.psycopg.connect", side_effect=psycopg.Error("down")):
        result = query_costs(_PG_URL, 7)
    assert result == _ZERO


def test_query_costs_uses_days_in_interval_sql() -> None:
    """The days value is embedded in the SQL INTERVAL clause."""
    conn = _mock_conn()
    conn.execute.return_value.fetchone.return_value = (0, 0, 0, 0, 0)
    with patch("src.db.costs.psycopg.connect", return_value=conn):
        query_costs(_PG_URL, 30)
    sql = conn.execute.call_args[0][0]
    assert "30 days" in sql


# --- endpoint tests ---

def test_costs_endpoint_returns_200_with_valid_key() -> None:
    """Valid X-Admin-Key + mocked query → 200 with all expected fields."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.costs.query_costs", return_value=_SAMPLE):
        with TestClient(app) as client:
            resp = client.get(
                "/admin/costs", headers={"X-Admin-Key": "changeme"}
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"] == "7d"
    assert body["total_requests"] == 5


def test_costs_endpoint_echoes_window_param() -> None:
    """The window query param is echoed back in the response body."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.costs.query_costs", return_value=_SAMPLE):
        with TestClient(app) as client:
            resp = client.get(
                "/admin/costs?window=14d", headers={"X-Admin-Key": "changeme"}
            )
    assert resp.json()["window"] == "14d"


def test_costs_endpoint_returns_401_without_key() -> None:
    """Missing X-Admin-Key header → 401."""
    app = create_app(settings=_make_mock_settings())
    with TestClient(app) as client:
        resp = client.get("/admin/costs")
    assert resp.status_code == 401


def test_costs_endpoint_returns_403_with_wrong_key() -> None:
    """Wrong X-Admin-Key value → 403."""
    app = create_app(settings=_make_mock_settings())
    with TestClient(app) as client:
        resp = client.get("/admin/costs", headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 403


def test_costs_endpoint_returns_422_for_invalid_window() -> None:
    """Non-Nd window format (e.g. 'abc') → 422 validation error."""
    app = create_app(settings=_make_mock_settings())
    with TestClient(app) as client:
        resp = client.get(
            "/admin/costs?window=abc", headers={"X-Admin-Key": "changeme"}
        )
    assert resp.status_code == 422
