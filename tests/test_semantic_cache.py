"""Tests for src/cache/semantic.py — all Redis and embedder interactions mocked."""

import json
from unittest.mock import MagicMock

import redis

from src.cache.semantic import cosine_similarity, semantic_search, semantic_store


def _mock_redis() -> MagicMock:
    return MagicMock(spec=redis.Redis)


def _mock_embedder(vec: list[float] | None = None) -> MagicMock:
    emb = MagicMock()
    emb.embed_query.return_value = vec if vec is not None else [1.0] + [0.0] * 511
    return emb


def _stored_entry(embedding: list[float]) -> str:
    return json.dumps({
        "answer": "cached answer",
        "sources": [{"title": "Docs", "url": "https://docs.stripe.com"}],
        "input_tokens": 100,
        "output_tokens": 20,
        "cost_usd": 0.0001,
        "embedding": embedding,
    })


# --- cosine_similarity ---

def test_cosine_similarity_identical_vectors() -> None:
    """Identical non-zero vectors have similarity 1.0."""
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors() -> None:
    """Orthogonal vectors have similarity 0.0."""
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_returns_zero() -> None:
    """Zero vector produces 0.0 without division error."""
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# --- semantic_search ---

def test_semantic_search_returns_none_when_no_entries() -> None:
    """Empty scan → no candidates → returns None."""
    client = _mock_redis()
    client.scan_iter.return_value = []
    result = semantic_search(client, _mock_embedder(), "how do I refund?", 0.95)
    assert result is None


def test_semantic_search_returns_hit_above_threshold() -> None:
    """Identical embedding with threshold 0.95 → returns cached result."""
    vec = [1.0] + [0.0] * 511
    client = _mock_redis()
    client.scan_iter.return_value = ["semantic:abc"]
    client.get.return_value = _stored_entry(vec)
    result = semantic_search(client, _mock_embedder(vec), "how do I refund?", 0.95)
    assert result is not None
    assert result["answer"] == "cached answer"


def test_semantic_search_returns_none_below_threshold() -> None:
    """Orthogonal embedding (sim=0.0) below threshold 0.95 → returns None."""
    query_vec = [1.0, 0.0]
    stored_vec = [0.0, 1.0]
    client = _mock_redis()
    client.scan_iter.return_value = ["semantic:abc"]
    client.get.return_value = _stored_entry(stored_vec)
    result = semantic_search(client, _mock_embedder(query_vec), "q?", 0.95)
    assert result is None


def test_semantic_search_strips_embedding_from_result() -> None:
    """Returned dict must not contain the 'embedding' field."""
    vec = [1.0] + [0.0] * 511
    client = _mock_redis()
    client.scan_iter.return_value = ["semantic:abc"]
    client.get.return_value = _stored_entry(vec)
    result = semantic_search(client, _mock_embedder(vec), "q?", 0.90)
    assert result is not None
    assert "embedding" not in result


def test_semantic_search_returns_none_on_redis_error() -> None:
    """Redis error during scan → returns None instead of raising."""
    client = _mock_redis()
    client.scan_iter.side_effect = redis.RedisError("connection lost")
    result = semantic_search(client, _mock_embedder(), "q?", 0.95)
    assert result is None


# --- semantic_store ---

def test_semantic_store_calls_setex_with_correct_ttl() -> None:
    """semantic_store calls redis.setex with the given TTL."""
    client = _mock_redis()
    semantic_store(client, _mock_embedder(), "q?", {"answer": "a"}, ttl=600)
    client.setex.assert_called_once()
    _, args, _ = client.setex.mock_calls[0]
    assert args[1] == 600


def test_semantic_store_key_has_semantic_prefix() -> None:
    """Stored key always starts with 'semantic:'."""
    client = _mock_redis()
    semantic_store(client, _mock_embedder(), "q?", {"answer": "a"}, ttl=60)
    key = client.setex.call_args[0][0]
    assert key.startswith("semantic:")


def test_semantic_store_includes_embedding_in_stored_value() -> None:
    """Stored JSON includes the 'embedding' field from embed_query."""
    client = _mock_redis()
    vec = [0.5, 0.5]
    semantic_store(client, _mock_embedder(vec), "q?", {"answer": "a"}, ttl=60)
    raw = client.setex.call_args[0][2]
    stored = json.loads(raw)
    assert stored["embedding"] == vec


def test_semantic_store_swallows_error() -> None:
    """Redis error during setex must not propagate to the caller."""
    client = _mock_redis()
    client.setex.side_effect = redis.RedisError("write failed")
    semantic_store(client, _mock_embedder(), "q?", {"answer": "a"}, ttl=60)
