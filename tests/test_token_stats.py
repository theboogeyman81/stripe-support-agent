"""Tests for src/cache/token_stats.py — all Redis interactions mocked."""

from unittest.mock import MagicMock

import redis

from src.cache.token_stats import (
    STATS_COST_MICROS,
    STATS_INPUT_TOKENS,
    STATS_OUTPUT_TOKENS,
    STATS_REQUESTS,
    accumulate,
    get_token_stats,
)


def _mock_redis() -> MagicMock:
    return MagicMock(spec=redis.Redis)


def _mock_redis_with_stats(
    inp: str | None = "100",
    out: str | None = "20",
    micros: str | None = "312",
    reqs: str | None = "1",
) -> MagicMock:
    values = {
        STATS_INPUT_TOKENS: inp,
        STATS_OUTPUT_TOKENS: out,
        STATS_COST_MICROS: micros,
        STATS_REQUESTS: reqs,
    }
    client = _mock_redis()
    client.get.side_effect = lambda key: values.get(key)
    return client


# --- accumulate ---

def test_accumulate_calls_incrby_for_input_tokens() -> None:
    """accumulate() calls redis.incrby for input_tokens with the correct value."""
    client = _mock_redis()
    accumulate(client, input_tokens=500, output_tokens=100, cost_usd=0.001)
    client.incrby.assert_any_call(STATS_INPUT_TOKENS, 500)


def test_accumulate_converts_cost_to_micros() -> None:
    """cost_usd is multiplied by 1_000_000 and stored as an integer."""
    client = _mock_redis()
    accumulate(client, input_tokens=0, output_tokens=0, cost_usd=0.001)
    client.incrby.assert_any_call(STATS_COST_MICROS, 1000)


def test_accumulate_no_ops_when_redis_none() -> None:
    """None redis_client returns without error."""
    accumulate(None, input_tokens=100, output_tokens=10, cost_usd=0.001)


def test_accumulate_swallows_redis_error() -> None:
    """Redis error during incrby must not propagate to the caller."""
    client = _mock_redis()
    client.incrby.side_effect = redis.RedisError("connection lost")
    accumulate(client, input_tokens=100, output_tokens=10, cost_usd=0.001)


# --- get_token_stats ---

def test_get_token_stats_returns_zeros_when_redis_none() -> None:
    """None redis_client → all fields are zero."""
    data = get_token_stats(None)
    assert data["total_input"] == 0
    assert data["total_output"] == 0
    assert data["total_cost_usd"] == 0.0
    assert data["total_requests"] == 0


def test_get_token_stats_returns_correct_values() -> None:
    """Counts from Redis are parsed and returned correctly."""
    client = _mock_redis_with_stats(inp="800", out="50", micros="300", reqs="2")
    data = get_token_stats(client)
    assert data["total_input"] == 800
    assert data["total_output"] == 50
    assert data["total_requests"] == 2


def test_get_token_stats_divides_micros_for_cost() -> None:
    """cost_micros is divided by 1_000_000 to produce total_cost_usd."""
    client = _mock_redis_with_stats(micros="1500")
    data = get_token_stats(client)
    assert abs(data["total_cost_usd"] - 0.0015) < 1e-9


def test_get_token_stats_returns_zeros_on_redis_error() -> None:
    """Redis error during get → all-zero response instead of raising."""
    client = _mock_redis()
    client.get.side_effect = redis.RedisError("down")
    data = get_token_stats(client)
    assert data["total_input"] == 0
    assert data["total_cost_usd"] == 0.0
