"""Tests for LoggingMiddleware — no network calls."""

import json
import logging
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app import create_app

_SAMPLE_CHUNKS = [
    {
        "chunk_id": "c1",
        "score": 0.9,
        "doc_url": "https://docs.stripe.com/refunds",
        "doc_title": "Refunds",
        "text": "refund text",
        "chunk_index": 0,
    }
]
_SAMPLE_GENERATE = {
    "answer": "Here is how to refund.",
    "input_tokens": 500,
    "output_tokens": 100,
    "cost_usd": 0.0004,
}


def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.qdrant_url = "http://localhost:6333"
    mock.qdrant_api_key = ""
    return mock


def test_logging_middleware_emits_json_log_on_ask(caplog) -> None:
    """POST /ask must produce a JSON log line with all 6 fields and a float cost_usd."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_SAMPLE_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=_SAMPLE_GENERATE):
        with caplog.at_level(logging.INFO, logger="src.api.middleware"):
            with TestClient(app) as client:
                client.post("/ask", json={"question": "What is a refund?"})
    log_line = json.loads(caplog.records[-1].message)
    assert log_line["path"] == "/ask"
    assert log_line["method"] == "POST"
    assert log_line["status_code"] == 200
    assert isinstance(log_line["cost_usd"], float)
    assert "request_id" in log_line
    assert "latency_ms" in log_line


def test_logging_middleware_cost_usd_null_for_health(caplog) -> None:
    """GET /health must produce a log line with cost_usd as null."""
    app = create_app(settings=_make_mock_settings())
    with caplog.at_level(logging.INFO, logger="src.api.middleware"):
        with TestClient(app) as client:
            client.get("/health")
    log_line = json.loads(caplog.records[-1].message)
    assert log_line["path"] == "/health"
    assert log_line["cost_usd"] is None


def test_logging_middleware_x_request_id_header_present() -> None:
    """Every response must carry an X-Request-ID header."""
    app = create_app(settings=_make_mock_settings())
    with TestClient(app) as client:
        response = client.get("/health")
    assert "x-request-id" in response.headers


def test_logging_middleware_status_code_logged_correctly(caplog) -> None:
    """A 422 validation error on /ask must log status_code=422 and cost_usd=null."""
    app = create_app(settings=_make_mock_settings())
    with caplog.at_level(logging.INFO, logger="src.api.middleware"):
        with TestClient(app) as client:
            client.post("/ask", json={"question": ""})  # triggers 422
    log_line = json.loads(caplog.records[-1].message)
    assert log_line["status_code"] == 422
    assert log_line["cost_usd"] is None
