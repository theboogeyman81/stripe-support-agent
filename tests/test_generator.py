"""Tests for src/rag/generator.py — all Gemini calls are mocked."""

import pytest
from unittest.mock import MagicMock, patch

from src.rag.generator import (
    INPUT_PRICE_PER_M,
    OUTPUT_PRICE_PER_M,
    build_prompt,
    generate,
)

_SAMPLE_CHUNKS = [
    {
        "chunk_id": "c1",
        "doc_title": "Refunds",
        "doc_url": "https://docs.stripe.com/refunds",
        "text": "To create a refund, use the Refunds API.",
        "score": 0.95,
        "chunk_index": 0,
    },
    {
        "chunk_id": "c2",
        "doc_title": "Payments",
        "doc_url": "https://docs.stripe.com/payments",
        "text": "A PaymentIntent tracks the lifecycle of a payment.",
        "score": 0.88,
        "chunk_index": 1,
    },
]


def test_build_prompt_includes_question():
    question = "How do I issue a refund?"
    prompt = build_prompt(question, _SAMPLE_CHUNKS)
    assert question in prompt


def test_build_prompt_includes_chunk_text():
    prompt = build_prompt("any question?", _SAMPLE_CHUNKS)
    for chunk in _SAMPLE_CHUNKS:
        assert chunk["text"] in prompt


def test_build_prompt_includes_chunk_urls():
    prompt = build_prompt("any question?", _SAMPLE_CHUNKS)
    for chunk in _SAMPLE_CHUNKS:
        assert chunk["doc_url"] in prompt


def _make_mock_response(input_tokens: int = 800, output_tokens: int = 50) -> MagicMock:
    mock = MagicMock()
    mock.text = "Here is how to create a refund [1]."
    mock.usage_metadata.prompt_token_count = input_tokens
    mock.usage_metadata.candidates_token_count = output_tokens
    return mock


def test_generate_returns_expected_shape():
    mock_response = _make_mock_response()
    with patch("src.rag.generator.genai.Client") as mock_cls, \
         patch("src.rag.generator.Settings"):
        mock_cls.return_value.models.generate_content.return_value = mock_response
        result = generate("How do I issue a refund?", _SAMPLE_CHUNKS)

    assert isinstance(result["answer"], str)
    assert len(result["answer"]) > 0
    assert isinstance(result["input_tokens"], int)
    assert isinstance(result["output_tokens"], int)
    assert isinstance(result["cost_usd"], float)


def test_generate_cost_calculation():
    input_tokens = 800
    output_tokens = 50
    mock_response = _make_mock_response(input_tokens, output_tokens)
    with patch("src.rag.generator.genai.Client") as mock_cls, \
         patch("src.rag.generator.Settings"):
        mock_cls.return_value.models.generate_content.return_value = mock_response
        result = generate("How do I issue a refund?", _SAMPLE_CHUNKS)

    expected = (input_tokens / 1_000_000) * INPUT_PRICE_PER_M + (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_M
    assert abs(result["cost_usd"] - expected) < 1e-10


def test_generate_raises_on_empty_question():
    with pytest.raises(ValueError, match="question must not be empty"):
        generate("", _SAMPLE_CHUNKS)


def test_generate_raises_on_empty_chunks():
    with pytest.raises(ValueError, match="chunks must not be empty"):
        generate("How do I issue a refund?", [])
