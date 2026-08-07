"""Tests for POST /feedback route — Langfuse client mocked, no network calls."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app import create_app


def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.api_host = "0.0.0.0"
    mock.api_port = 8000
    return mock


def test_feedback_returns_200_on_success() -> None:
    """POST /feedback with valid body returns 200 and success=true."""
    mock_client = MagicMock()
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.feedback.get_langfuse_client", return_value=mock_client):
        with TestClient(app) as client:
            response = client.post(
                "/feedback",
                json={"trace_id": "trace-abc", "value": 1},
            )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_feedback_calls_create_score_with_correct_args() -> None:
    """POST /feedback must forward trace_id, name, value, and comment to create_score."""
    mock_client = MagicMock()
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.feedback.get_langfuse_client", return_value=mock_client):
        with TestClient(app) as client:
            client.post(
                "/feedback",
                json={"trace_id": "t1", "value": 0, "comment": "bad answer"},
            )
    mock_client.create_score.assert_called_once_with(
        trace_id="t1",
        name="user-feedback",
        value=0,
        comment="bad answer",
    )
    mock_client.flush.assert_called_once()


def test_feedback_returns_503_when_langfuse_absent() -> None:
    """POST /feedback must return 503 when Langfuse is not configured."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.feedback.get_langfuse_client", return_value=None):
        with TestClient(app) as client:
            response = client.post(
                "/feedback",
                json={"trace_id": "trace-xyz", "value": 1},
            )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
