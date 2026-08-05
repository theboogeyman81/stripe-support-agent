"""Tests for src/api/error_handlers.py — no network calls."""

import logging
from unittest.mock import MagicMock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.app import create_app


def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.qdrant_url = "http://localhost:6333"
    mock.qdrant_api_key = ""
    return mock


def _app_with_error_route():
    """Return an app that has a route guaranteed to raise RuntimeError."""
    app = create_app(settings=_make_mock_settings())

    def _raise_runtime_error():
        raise RuntimeError("secret internal detail")

    def _raise_http_502():
        raise HTTPException(status_code=502, detail="upstream failed")

    app.add_api_route("/trigger-error", _raise_runtime_error, methods=["GET"])
    app.add_api_route("/trigger-http", _raise_http_502, methods=["GET"])
    return app


def test_unhandled_exception_returns_500() -> None:
    """An unhandled RuntimeError must produce HTTP 500."""
    app = _app_with_error_route()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/trigger-error")
    assert response.status_code == 500


def test_unhandled_exception_body_is_safe() -> None:
    """The 500 body must be generic and must not leak the exception message."""
    app = _app_with_error_route()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/trigger-error")
    body = response.json()
    assert body == {"detail": "internal server error"}
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text


def test_unhandled_exception_is_logged(caplog) -> None:
    """The handler must log at ERROR level with exc_info so the traceback is captured."""
    app = _app_with_error_route()
    with caplog.at_level(logging.ERROR, logger="src.api.error_handlers"):
        with TestClient(app, raise_server_exceptions=False) as client:
            client.get("/trigger-error")
    assert len(caplog.records) >= 1
    error_record = caplog.records[-1]
    assert error_record.levelno == logging.ERROR
    assert error_record.exc_info is not None


def test_http_exception_not_intercepted() -> None:
    """An explicit HTTPException must pass through with its own status and detail."""
    app = _app_with_error_route()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/trigger-http")
    assert response.status_code == 502
    assert response.json()["detail"] == "upstream failed"


def test_validation_error_not_intercepted() -> None:
    """A missing required field must still return 422, not 500."""
    app = _app_with_error_route()
    with TestClient(app) as client:
        response = client.post("/ask", json={})
    assert response.status_code == 422
