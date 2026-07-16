"""Tests for POST /ask route — no network calls, retrieve and generate mocked."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app import create_app

_SAMPLE_CHUNKS = [
    {
        "chunk_id": "c1",
        "score": 0.95,
        "doc_url": "https://docs.stripe.com/refunds",
        "doc_title": "Refunds",
        "text": "To create a refund...",
        "chunk_index": 0,
    },
    {
        "chunk_id": "c2",
        "score": 0.88,
        "doc_url": "https://docs.stripe.com/disputes",
        "doc_title": "Disputes",
        "text": "A dispute occurs...",
        "chunk_index": 1,
    },
]

_SAMPLE_GENERATE = {
    "answer": "You can create a refund via the API.",
    "input_tokens": 500,
    "output_tokens": 100,
    "cost_usd": 0.0004,
}


def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.api_host = "0.0.0.0"
    mock.api_port = 8000
    return mock


def test_ask_returns_200_with_expected_shape() -> None:
    """POST /ask with a valid question returns 200 with answer, sources, and cost."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_SAMPLE_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=_SAMPLE_GENERATE):
        with TestClient(app) as client:
            response = client.post("/ask", json={"question": "How do I refund?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == _SAMPLE_GENERATE["answer"]
    assert body["input_tokens"] == 500
    assert body["output_tokens"] == 100
    assert body["cost_usd"] == 0.0004
    assert len(body["sources"]) == 2
    assert body["sources"][0]["url"] == "https://docs.stripe.com/refunds"


def test_ask_empty_question_returns_422() -> None:
    """POST /ask with an empty question must return 422 before reaching the handler."""
    app = create_app(settings=_make_mock_settings())
    with TestClient(app) as client:
        response = client.post("/ask", json={"question": ""})
    assert response.status_code == 422


def test_ask_top_k_default_is_five() -> None:
    """retrieve() must be called with top_k=5 when top_k is omitted from the request."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_SAMPLE_CHUNKS) as mock_retrieve, \
         patch("src.api.routes.ask.generate", return_value=_SAMPLE_GENERATE):
        with TestClient(app) as client:
            client.post("/ask", json={"question": "test"})
    mock_retrieve.assert_called_once_with("test", 5)


def test_ask_sources_deduplicated_by_url() -> None:
    """Sources with the same URL must appear only once in the response."""
    duplicate_chunks = [
        {**_SAMPLE_CHUNKS[0]},
        {**_SAMPLE_CHUNKS[0], "chunk_id": "c1b", "chunk_index": 1},
    ]
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=duplicate_chunks), \
         patch("src.api.routes.ask.generate", return_value=_SAMPLE_GENERATE):
        with TestClient(app) as client:
            response = client.post("/ask", json={"question": "test"})
    assert response.status_code == 200
    assert len(response.json()["sources"]) == 1


def test_ask_upstream_error_returns_502() -> None:
    """Any exception from retrieve() must produce a 502 with an upstream error detail."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", side_effect=RuntimeError("Qdrant down")):
        with TestClient(app) as client:
            response = client.post("/ask", json={"question": "test"})
    assert response.status_code == 502
    assert "upstream error" in response.json()["detail"]
