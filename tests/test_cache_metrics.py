"""Tests for src/cache/metrics.py — all Redis interactions mocked."""

from unittest.mock import MagicMock

import pytest
import redis

from src.cache.metrics import (
    EXACT_HITS,
    EXACT_MISSES,
    SEMANTIC_HITS,
    SEMANTIC_MISSES,
    get_metrics,
    increment,
)


def _mock_redis() -> MagicMock:
    return MagicMock(spec=redis.Redis)


def _mock_redis_with_counts(
    sem_hits: str | None = "0",
    sem_misses: str | None = "0",
    exact_hits: str | None = "0",
    exact_misses: str | None = "0",
) -> MagicMock:
    values = {
        SEMANTIC_HITS: sem_hits,
        SEMANTIC_MISSES: sem_misses,
        EXACT_HITS: exact_hits,
        EXACT_MISSES: exact_misses,
    }
    client = _mock_redis()
    client.get.side_effect = lambda key: values.get(key)
    return client


# --- increment ---

def test_increment_calls_redis_incr() -> None:
    """increment() calls redis.incr with the given key."""
    client = _mock_redis()
    increment(client, SEMANTIC_HITS)
    client.incr.assert_called_once_with(SEMANTIC_HITS)


def test_increment_no_ops_when_redis_none() -> None:
    """increment() with None client returns without error."""
    increment(None, SEMANTIC_HITS)  # must not raise


def test_increment_swallows_redis_error() -> None:
    """Redis error during incr must not propagate to the caller."""
    client = _mock_redis()
    client.incr.side_effect = redis.RedisError("connection lost")
    increment(client, SEMANTIC_HITS)  # must not raise


# --- get_metrics ---

def test_get_metrics_returns_zeros_when_redis_none() -> None:
    """None redis_client → all counts and rates are zero."""
    data = get_metrics(None)
    assert data["semantic"]["hits"] == 0
    assert data["semantic"]["misses"] == 0
    assert data["semantic"]["hit_rate"] == 0.0
    assert data["exact"]["hits"] == 0
    assert data["total_requests"] == 0


def test_get_metrics_returns_zeros_on_redis_error() -> None:
    """Redis error during get → all-zero response instead of raising."""
    client = _mock_redis()
    client.get.side_effect = redis.RedisError("down")
    data = get_metrics(client)
    assert data["semantic"]["hits"] == 0
    assert data["total_requests"] == 0


def test_get_metrics_returns_correct_counts() -> None:
    """Counts from Redis are parsed and returned correctly."""
    client = _mock_redis_with_counts("5", "20", "3", "17")
    data = get_metrics(client)
    assert data["semantic"]["hits"] == 5
    assert data["semantic"]["misses"] == 20
    assert data["exact"]["hits"] == 3
    assert data["exact"]["misses"] == 17


def test_get_metrics_hit_rate_correct() -> None:
    """hit_rate = hits / (hits + misses)."""
    client = _mock_redis_with_counts(sem_hits="3", sem_misses="1")
    data = get_metrics(client)
    assert abs(data["semantic"]["hit_rate"] - 0.75) < 1e-9


def test_get_metrics_hit_rate_zero_when_no_requests() -> None:
    """0 hits and 0 misses → hit_rate is 0.0, not a division error."""
    client = _mock_redis_with_counts("0", "0", "0", "0")
    data = get_metrics(client)
    assert data["semantic"]["hit_rate"] == 0.0
    assert data["exact"]["hit_rate"] == 0.0


def test_get_metrics_total_requests_is_semantic_total() -> None:
    """total_requests equals semantic hits + semantic misses."""
    client = _mock_redis_with_counts(sem_hits="4", sem_misses="6")
    data = get_metrics(client)
    assert data["total_requests"] == 10


def test_get_metrics_missing_key_treated_as_zero() -> None:
    """redis.get returning None (key never set) is treated as 0."""
    client = _mock_redis_with_counts(
        sem_hits=None, sem_misses=None, exact_hits=None, exact_misses=None
    )
    data = get_metrics(client)
    assert data["semantic"]["hits"] == 0
    assert data["exact"]["hits"] == 0
    assert data["total_requests"] == 0
