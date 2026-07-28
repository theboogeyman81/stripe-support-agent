"""Tests for src/api/schemas.py — pure Pydantic validation, no network calls."""

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    AskRequest,
    AskResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    ReadyCheck,
    ReadyResponse,
    SourceItem,
)


def test_ask_request_valid():
    req = AskRequest(question="How do I create a PaymentIntent?", top_k=3)
    assert req.question == "How do I create a PaymentIntent?"
    assert req.top_k == 3


def test_ask_request_missing_question():
    with pytest.raises(ValidationError):
        AskRequest(top_k=5)


def test_ask_request_empty_question():
    with pytest.raises(ValidationError):
        AskRequest(question="")


def test_ask_request_top_k_below_minimum():
    with pytest.raises(ValidationError):
        AskRequest(question="test", top_k=0)


def test_ask_request_top_k_default():
    req = AskRequest(question="test")
    assert req.top_k == 5


def test_ask_response_valid():
    source = SourceItem(title="PaymentIntents", url="https://docs.stripe.com/payments/payment-intents")
    resp = AskResponse(
        answer="Call stripe.paymentIntents.create().",
        sources=[source],
        input_tokens=512,
        output_tokens=64,
        cost_usd=0.0002,
    )
    assert resp.answer == "Call stripe.paymentIntents.create()."
    assert len(resp.sources) == 1
    assert resp.sources[0].title == "PaymentIntents"


def test_ingest_request_defaults():
    req = IngestRequest()
    assert req.recreate is False


def test_ingest_response_valid():
    resp = IngestResponse(
        docs_loaded=1,
        chunks_produced=4319,
        vectors_embedded=4319,
        vectors_skipped=0,
        points_upserted=4319,
        embed_cost_usd=0.0,
        cached_steps=[],
    )
    assert resp.chunks_produced == 4319
    assert resp.cached_steps == []


def test_health_response_valid():
    resp = HealthResponse(status="ok")
    assert resp.status == "ok"


def test_ready_response_valid():
    resp = ReadyResponse(status="ok", checks=ReadyCheck(qdrant="ok"))
    assert resp.status == "ok"
    assert resp.checks.qdrant == "ok"


def test_ready_response_degraded():
    resp = ReadyResponse(status="degraded", checks=ReadyCheck(qdrant="unreachable"))
    assert resp.checks.qdrant == "unreachable"


def test_models_have_field_descriptions():
    fields = AskRequest.model_fields
    for name, field_info in fields.items():
        assert field_info.description, f"AskRequest.{name} is missing a description"
