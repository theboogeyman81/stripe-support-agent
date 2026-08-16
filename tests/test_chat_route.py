"""Tests for POST /chat route — run_agent mocked, no network calls."""

from unittest.mock import MagicMock, call, patch

from fastapi.testclient import TestClient

from src.api.app import create_app

_SAMPLE_RESULT = {
    "answer": "Use PaymentIntents for card payments.",
    "input_tokens": 400,
    "output_tokens": 80,
    "cost_usd": 0.0003,
    "message_history": [{"kind": "request", "messages": []}],
}

_SAMPLE_RESULT_2 = {
    "answer": "As I mentioned, PaymentIntents handle the payment flow.",
    "input_tokens": 500,
    "output_tokens": 90,
    "cost_usd": 0.0004,
    "message_history": [
        {"kind": "request", "messages": []},
        {"kind": "response", "messages": []},
    ],
}


def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.api_host = "0.0.0.0"
    mock.api_port = 8000
    return mock


def test_chat_returns_200_with_expected_shape() -> None:
    """POST /chat with a valid question returns 200 with session_id, answer, and cost."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.chat._sessions", {}), \
         patch("src.api.routes.chat.run_agent", return_value=_SAMPLE_RESULT):
        with TestClient(app) as client:
            response = client.post("/chat", json={"question": "What is a PaymentIntent?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == _SAMPLE_RESULT["answer"]
    assert body["input_tokens"] == 400
    assert body["output_tokens"] == 80
    assert body["cost_usd"] == 0.0003
    assert "session_id" in body and body["session_id"]


def test_chat_generates_session_id_when_omitted() -> None:
    """Omitting session_id in the request must produce a non-empty session_id in response."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.chat._sessions", {}), \
         patch("src.api.routes.chat.run_agent", return_value=_SAMPLE_RESULT):
        with TestClient(app) as client:
            response = client.post("/chat", json={"question": "hello"})
    assert response.status_code == 200
    assert response.json()["session_id"] != ""


def test_chat_reuses_existing_session() -> None:
    """Second call with the same session_id must pass non-empty history to run_agent."""
    app = create_app(settings=_make_mock_settings())
    sessions: dict = {}
    with patch("src.api.routes.chat._sessions", sessions), \
         patch(
             "src.api.routes.chat.run_agent",
             side_effect=[_SAMPLE_RESULT, _SAMPLE_RESULT_2],
         ) as mock_run:
        with TestClient(app) as client:
            r1 = client.post("/chat", json={"question": "first question"})
            sid = r1.json()["session_id"]
            client.post("/chat", json={"session_id": sid, "question": "follow up"})
    _, second_call_kwargs = mock_run.call_args_list[1]
    assert second_call_kwargs["message_history"] == _SAMPLE_RESULT["message_history"]


def test_chat_empty_question_returns_422() -> None:
    """POST /chat with an empty question must return 422 before reaching the handler."""
    app = create_app(settings=_make_mock_settings())
    with TestClient(app) as client:
        response = client.post("/chat", json={"question": ""})
    assert response.status_code == 422


def test_chat_upstream_error_returns_502() -> None:
    """Any exception from run_agent must produce a 502 with upstream error detail."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.chat._sessions", {}), \
         patch("src.api.routes.chat.run_agent", side_effect=RuntimeError("Gemini down")):
        with TestClient(app) as client:
            response = client.post("/chat", json={"question": "test"})
    assert response.status_code == 502
    assert "upstream error" in response.json()["detail"]


def test_chat_unknown_session_id_starts_new_session() -> None:
    """An unrecognised session_id must be treated as a new session, not a 404."""
    app = create_app(settings=_make_mock_settings())
    with patch("src.api.routes.chat._sessions", {}), \
         patch("src.api.routes.chat.run_agent", return_value=_SAMPLE_RESULT):
        with TestClient(app) as client:
            response = client.post(
                "/chat",
                json={"session_id": "nonexistent-id", "question": "hello"},
            )
    assert response.status_code == 200
    assert response.json()["session_id"] != "nonexistent-id"
