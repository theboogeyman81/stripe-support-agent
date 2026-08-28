"""Tests for fallback chain in src/rag/generator.py — all Gemini calls are mocked."""

from unittest.mock import MagicMock, patch

from src.rag.generator import APOLOGY_ANSWER, generate

_SAMPLE_CHUNKS = [
    {
        "chunk_id": "c1",
        "doc_title": "Refunds",
        "doc_url": "https://docs.stripe.com/refunds",
        "text": "To create a refund, use the Refunds API.",
        "score": 0.95,
        "chunk_index": 0,
    },
]

_VALID_RESULT = {
    "answer": "Here is the answer about refunds.",
    "input_tokens": 100,
    "output_tokens": 20,
    "cost_usd": 0.00008,
}


def test_primary_success_fallback_level_zero():
    with patch("src.rag.generator._call_model", return_value=_VALID_RESULT.copy()), \
         patch("src.rag.generator.Settings"):
        result = generate("How do I refund?", _SAMPLE_CHUNKS)
    assert result["fallback_level"] == 0
    assert result["answer"] == _VALID_RESULT["answer"]


def test_primary_fails_secondary_succeeds():
    secondary_result = {**_VALID_RESULT, "answer": "Secondary answer."}
    with patch("src.rag.generator._call_model") as mock_call, \
         patch("src.rag.generator.Settings"):
        mock_call.side_effect = [Exception("rate limit"), secondary_result.copy()]
        result = generate("How do I refund?", _SAMPLE_CHUNKS)
    assert result["fallback_level"] == 1
    assert result["answer"] == "Secondary answer."


def test_both_models_fail_returns_apology():
    with patch("src.rag.generator._call_model") as mock_call, \
         patch("src.rag.generator.Settings"):
        mock_call.side_effect = [Exception("primary down"), Exception("secondary down")]
        result = generate("How do I refund?", _SAMPLE_CHUNKS)
    assert result["fallback_level"] == 2
    assert result["answer"] == APOLOGY_ANSWER


def test_apology_not_cached():
    mock_redis = MagicMock()
    with patch("src.rag.generator._call_model") as mock_call, \
         patch("src.rag.generator.Settings"), \
         patch("src.rag.generator.get_cached", return_value=None), \
         patch("src.rag.generator.set_cached") as mock_set:
        mock_call.side_effect = [Exception("fail1"), Exception("fail2")]
        generate("How do I refund?", _SAMPLE_CHUNKS, redis_client=mock_redis)
    mock_set.assert_not_called()


def test_apology_zero_tokens_zero_cost():
    with patch("src.rag.generator._call_model") as mock_call, \
         patch("src.rag.generator.Settings"):
        mock_call.side_effect = [Exception("fail1"), Exception("fail2")]
        result = generate("How do I refund?", _SAMPLE_CHUNKS)
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["cost_usd"] == 0.0


def test_secondary_result_cached():
    mock_redis = MagicMock()
    mock_redis.exists.return_value = 0  # circuit closed — primary is tried first
    secondary_result = _VALID_RESULT.copy()
    with patch("src.rag.generator._call_model") as mock_call, \
         patch("src.rag.generator.Settings"), \
         patch("src.rag.generator.get_cached", return_value=None), \
         patch("src.rag.generator.set_cached") as mock_set:
        mock_call.side_effect = [Exception("primary down"), secondary_result]
        generate("How do I refund?", _SAMPLE_CHUNKS, redis_client=mock_redis)
    mock_set.assert_called_once()
