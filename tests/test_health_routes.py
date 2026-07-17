"""Tests for GET /health and GET /ready routes — no network calls."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app import create_app


def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.qdrant_url = "http://localhost:6333"
    mock.qdrant_api_key = ""
    return mock


def test_health_returns_200_with_ok_status() -> None:
    """GET /health must always return 200 with {"status": "ok"}."""
    app = create_app(settings=_make_mock_settings())
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_200_when_qdrant_reachable() -> None:
    """GET /ready returns 200 with ok status when ping() succeeds."""
    app = create_app(settings=_make_mock_settings())
    mock_store = MagicMock()
    mock_store.ping.return_value = True
    with patch("src.api.routes.health.QdrantStore", return_value=mock_store):
        with TestClient(app) as client:
            response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["qdrant"] == "ok"


def test_ready_returns_503_when_qdrant_unreachable() -> None:
    """GET /ready returns 503 with degraded status when ping() raises."""
    app = create_app(settings=_make_mock_settings())
    mock_store = MagicMock()
    mock_store.ping.side_effect = Exception("down")
    with patch("src.api.routes.health.QdrantStore", return_value=mock_store):
        with TestClient(app) as client:
            response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["qdrant"] == "unreachable"
