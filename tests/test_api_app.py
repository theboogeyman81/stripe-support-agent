"""Tests for src/api/app.py — no network calls, Settings always mocked."""

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.app import APP_VERSION, create_app


def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.api_host = "0.0.0.0"
    mock.api_port = 8000
    return mock


def test_create_app_returns_fastapi_instance() -> None:
    """create_app() must return a FastAPI object."""
    assert isinstance(create_app(settings=_make_mock_settings()), FastAPI)


def test_app_title_and_version() -> None:
    """FastAPI app must have correct title and version metadata."""
    app = create_app(settings=_make_mock_settings())
    assert app.title == "Stripe Support Agent"
    assert app.version == APP_VERSION


def test_root_endpoint_returns_ok() -> None:
    """GET / must return 200 with the expected status/service/version payload."""
    app = create_app(settings=_make_mock_settings())
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "stripe-support-agent"
    assert body["version"] == APP_VERSION


def test_app_state_has_settings_after_startup() -> None:
    """app.state.settings must be the exact Settings instance passed to create_app."""
    mock_settings = _make_mock_settings()
    app = create_app(settings=mock_settings)
    with TestClient(app) as client:
        client.get("/")
    assert app.state.settings is mock_settings
