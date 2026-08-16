"""Tests for src/cache/exact_match.py — all Redis interactions mocked."""

import json
from unittest.mock import MagicMock

import redis

from src.cache.exact_match import cache_key, get_cached, set_cached


def _mock_redis() -> MagicMock:
    return MagicMock(spec=redis.Redis)


# --- cache_key ---

def test_cache_key_is_deterministic() -> None:
    """Same model and prompt always produce the same key."""
    k1 = cache_key("gemini-2.5-flash", "some prompt")
    k2 = cache_key("gemini-2.5-flash", "some prompt")
    assert k1 == k2


def test_cache_key_differs_by_model() -> None:
    """Different model names produce different keys."""
    k1 = cache_key("gemini-2.5-flash", "prompt")
    k2 = cache_key("gemini-2.0-flash", "prompt")
    assert k1 != k2


def test_cache_key_differs_by_prompt() -> None:
    """Different prompts produce different keys."""
    k1 = cache_key("model", "question A")
    k2 = cache_key("model", "question B")
    assert k1 != k2


def test_cache_key_has_exact_prefix() -> None:
    """Cache key always starts with 'exact:'."""
    assert cache_key("model", "prompt").startswith("exact:")


# --- get_cached ---

def test_get_cached_returns_none_on_miss() -> None:
    """Redis returning None (key absent) → get_cached returns None."""
    client = _mock_redis()
    client.get.return_value = None
    assert get_cached(client, "exact:abc") is None


def test_get_cached_returns_dict_on_hit() -> None:
    """Redis returning a JSON string → get_cached returns parsed dict."""
    client = _mock_redis()
    payload = {"answer": "yes", "input_tokens": 10, "output_tokens": 5}
    client.get.return_value = json.dumps(payload)
    result = get_cached(client, "exact:abc")
    assert result == payload


def test_get_cached_returns_none_on_redis_error() -> None:
    """Redis raising an error → get_cached returns None instead of raising."""
    client = _mock_redis()
    client.get.side_effect = redis.RedisError("connection lost")
    assert get_cached(client, "exact:abc") is None


def test_get_cached_returns_none_on_corrupt_json() -> None:
    """Corrupt cached value → treated as miss, returns None."""
    client = _mock_redis()
    client.get.return_value = "not valid json{"
    assert get_cached(client, "exact:abc") is None


# --- set_cached ---

def test_set_cached_calls_setex_with_ttl() -> None:
    """set_cached calls redis.setex with the key, ttl, and JSON-encoded value."""
    client = _mock_redis()
    value = {"answer": "yes", "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001}
    set_cached(client, "exact:abc", value, ttl=600)
    client.setex.assert_called_once()
    args = client.setex.call_args[0]
    assert args[0] == "exact:abc"
    assert args[1] == 600
    stored = json.loads(args[2])
    assert stored["answer"] == "yes"


def test_set_cached_strips_cache_hit_field() -> None:
    """set_cached does not persist the cache_hit annotation."""
    client = _mock_redis()
    value = {"answer": "yes", "cache_hit": False, "cost_usd": 0.001}
    set_cached(client, "exact:abc", value, ttl=60)
    args = client.setex.call_args[0]
    stored = json.loads(args[2])
    assert "cache_hit" not in stored


def test_set_cached_swallows_redis_error() -> None:
    """Redis error during write must not propagate to the caller."""
    client = _mock_redis()
    client.setex.side_effect = redis.RedisError("write failed")
    set_cached(client, "exact:abc", {"answer": "x"}, ttl=60)  # must not raise
