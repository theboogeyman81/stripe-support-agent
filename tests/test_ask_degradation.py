"""Tests for degradation fields in POST /ask — all upstream calls mocked."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.rag.generator import APOLOGY_ANSWER

_SAMPLE_CHUNKS = [
    {
        "chunk_id": "c1",
        "score": 0.95,
        "doc_url": "https://docs.stripe.com/refunds",
        "doc_title": "Refunds",
        "text": "Stripe Refunds API allows you to create refunds programmatically.",
        "chunk_index": 0,
    }
]

# Chunks whose text overlaps the apology answer so grounding passes without mocking.
_APOLOGY_CHUNKS = [
    {
        "chunk_id": "c1",
        "score": 0.95,
        "doc_url": "https://docs.stripe.com/support",
        "doc_title": "Stripe Support",
        "text": "Contact Stripe support directly for additional help.",
        "chunk_index": 0,
    }
]

_HEALTHY_GENERATE = {
    "answer": "You can create a refund via the Stripe Refunds API.",
    "input_tokens": 500,
    "output_tokens": 100,
    "cost_usd": 0.0004,
    "cache_hit": False,
    "fallback_level": 0,
}


def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.api_host = "0.0.0.0"
    mock.api_port = 8000
    return mock


def _post(client, question: str = "How do I create a refund?") -> dict:
    return client.post("/ask", json={"question": question})


def test_happy_path_not_degraded() -> None:
    """Normal answer returns degraded=False, reason=None, fallback_level=0."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_SAMPLE_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=_HEALTHY_GENERATE.copy()):
        with TestClient(app) as client:
            response = _post(client)
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is False
    assert body["degradation_reason"] is None
    assert body["fallback_level"] == 0


def test_unsafe_answer_sets_degraded() -> None:
    """Answer containing profanity sets degraded=True, reason='unsafe_output'."""
    unsafe_generate = {**_HEALTHY_GENERATE, "answer": "fuck this API"}
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_SAMPLE_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=unsafe_generate):
        with TestClient(app) as client:
            response = _post(client)
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert body["degradation_reason"] == "unsafe_output"


def test_ungrounded_answer_sets_degraded() -> None:
    """Answer with no overlap against chunks sets degraded=True, reason='ungrounded'."""
    ungrounded_generate = {
        **_HEALTHY_GENERATE,
        "answer": "The weather today is sunny and warm.",
    }
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_SAMPLE_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=ungrounded_generate):
        with TestClient(app) as client:
            response = _post(client)
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert body["degradation_reason"] == "ungrounded"


def test_uncited_answer_sets_degraded() -> None:
    """Citation enforcement failure sets degraded=True, reason='uncited'."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_SAMPLE_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=_HEALTHY_GENERATE.copy()), \
         patch("src.api.routes.ask.enforce_citation", return_value=False):
        with TestClient(app) as client:
            response = _post(client)
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert body["degradation_reason"] == "uncited"


def test_secondary_model_sets_degraded() -> None:
    """fallback_level=1 sets degraded=True, degradation_reason='model_fallback'."""
    secondary_generate = {**_HEALTHY_GENERATE, "fallback_level": 1}
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_SAMPLE_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=secondary_generate):
        with TestClient(app) as client:
            response = _post(client)
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert body["degradation_reason"] == "model_fallback"
    assert body["fallback_level"] == 1


def test_apology_sets_service_unavailable() -> None:
    """fallback_level=2 with apology answer sets reason='service_unavailable'."""
    apology_generate = {
        **_HEALTHY_GENERATE,
        "answer": APOLOGY_ANSWER,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "fallback_level": 2,
    }
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_APOLOGY_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=apology_generate):
        with TestClient(app) as client:
            response = _post(client)
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert body["degradation_reason"] == "service_unavailable"
    assert body["fallback_level"] == 2


def test_retry_after_header_on_apology() -> None:
    """Retry-After: 60 header is present when fallback_level=2."""
    apology_generate = {
        **_HEALTHY_GENERATE,
        "answer": APOLOGY_ANSWER,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "fallback_level": 2,
    }
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_APOLOGY_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=apology_generate):
        with TestClient(app) as client:
            response = _post(client)
    assert response.headers.get("retry-after") == "60"


def test_no_retry_after_on_secondary_model() -> None:
    """Retry-After header is absent when fallback_level=1."""
    secondary_generate = {**_HEALTHY_GENERATE, "fallback_level": 1}
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_SAMPLE_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=secondary_generate):
        with TestClient(app) as client:
            response = _post(client)
    assert "retry-after" not in response.headers


def test_fallback_level_propagated_in_response() -> None:
    """fallback_level from generate() is surfaced in the response body."""
    secondary_generate = {**_HEALTHY_GENERATE, "fallback_level": 1}
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.ask.retrieve", return_value=_SAMPLE_CHUNKS), \
         patch("src.api.routes.ask.generate", return_value=secondary_generate):
        with TestClient(app) as client:
            response = _post(client)
    assert response.json()["fallback_level"] == 1
