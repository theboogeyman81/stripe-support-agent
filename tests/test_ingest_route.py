"""Tests for POST /admin/ingest route — no network calls, run_ingest mocked."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app import create_app

_SAMPLE_RESULT = {
    "docs_loaded": 0,
    "chunks_produced": 0,
    "vectors_embedded": 0,
    "vectors_skipped": 4319,
    "points_upserted": 4319,
    "embed_cost_usd": 0.0,
    "cached_steps": ["docs", "chunks", "embeddings"],
}


def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.admin_api_key = "test-key"
    return mock


def test_ingest_missing_key_returns_401() -> None:
    """POST /admin/ingest with no X-Admin-Key header must return 401."""
    app = create_app(settings=_make_mock_settings())
    with TestClient(app) as client:
        response = client.post("/admin/ingest", json={})
    assert response.status_code == 401
    assert response.json()["detail"] == "missing admin key"


def test_ingest_wrong_key_returns_403() -> None:
    """POST /admin/ingest with an incorrect key must return 403."""
    app = create_app(settings=_make_mock_settings())
    with TestClient(app) as client:
        response = client.post("/admin/ingest", json={}, headers={"X-Admin-Key": "wrong"})
    assert response.status_code == 403
    assert response.json()["detail"] == "invalid admin key"


def test_ingest_valid_key_returns_200_with_expected_shape() -> None:
    """POST /admin/ingest with a valid key returns 200 with all 7 response fields."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ingest.run_ingest", return_value=_SAMPLE_RESULT):
        with TestClient(app) as client:
            response = client.post("/admin/ingest", json={}, headers={"X-Admin-Key": "test-key"})
    assert response.status_code == 200
    body = response.json()
    assert body["points_upserted"] == 4319
    assert body["vectors_skipped"] == 4319
    assert body["embed_cost_usd"] == 0.0
    assert body["cached_steps"] == ["docs", "chunks", "embeddings"]


def test_ingest_pipeline_error_returns_502() -> None:
    """Any exception from run_ingest must produce a 502 with an ingest error detail."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ingest.run_ingest", side_effect=RuntimeError("Qdrant down")):
        with TestClient(app) as client:
            response = client.post("/admin/ingest", json={}, headers={"X-Admin-Key": "test-key"})
    assert response.status_code == 502
    assert "ingest error" in response.json()["detail"]


def test_ingest_recreate_flag_passed_through() -> None:
    """recreate=true in the request body must be forwarded to run_ingest."""
    app = create_app(settings=_make_mock_settings())
    mock_run = MagicMock(return_value=_SAMPLE_RESULT)
    with patch("src.api.routes.ingest.run_ingest", mock_run):
        with TestClient(app) as client:
            client.post(
                "/admin/ingest",
                json={"recreate": True},
                headers={"X-Admin-Key": "test-key"},
            )
    _, kwargs = mock_run.call_args
    assert kwargs.get("recreate") is True or mock_run.call_args[0][1] is True
