"""Tests for src/cache/redis_client.py — Redis client factory."""

from unittest.mock import MagicMock, patch

import pytest

from src.cache.redis_client import get_redis_client
from src.config import Settings


def _settings(redis_url: str = "rediss://default:pw@host:6380") -> Settings:
    return Settings(
        gemini_api_key="g",
        voyage_api_key="v",
        qdrant_url="http://localhost",
        redis_url=redis_url,
    )


def test_raises_value_error_when_redis_url_empty() -> None:
    """Empty REDIS_URL raises ValueError before attempting a connection."""
    with pytest.raises(ValueError, match="REDIS_URL"):
        get_redis_client(_settings(redis_url=""))


def test_from_url_called_with_correct_url() -> None:
    """Factory passes settings.redis_url to redis.Redis.from_url."""
    url = "rediss://default:pw@host:6380"
    with patch("src.cache.redis_client.redis.Redis") as mock_redis:
        mock_redis.from_url.return_value = MagicMock()
        get_redis_client(_settings(redis_url=url))
        args, _ = mock_redis.from_url.call_args
        assert args[0] == url


def test_decode_responses_is_true() -> None:
    """Factory always sets decode_responses=True so values are str, not bytes."""
    with patch("src.cache.redis_client.redis.Redis") as mock_redis:
        mock_redis.from_url.return_value = MagicMock()
        get_redis_client(_settings())
        _, kwargs = mock_redis.from_url.call_args
        assert kwargs["decode_responses"] is True


def test_ssl_cert_reqs_is_none() -> None:
    """Factory sets ssl_cert_reqs=None to accept Redis Cloud self-signed certs."""
    with patch("src.cache.redis_client.redis.Redis") as mock_redis:
        mock_redis.from_url.return_value = MagicMock()
        get_redis_client(_settings())
        _, kwargs = mock_redis.from_url.call_args
        assert kwargs["ssl_cert_reqs"] is None


def test_returns_redis_instance() -> None:
    """Factory returns the client object produced by redis.Redis.from_url."""
    mock_client = MagicMock()
    with patch("src.cache.redis_client.redis.Redis") as mock_redis:
        mock_redis.from_url.return_value = mock_client
        result = get_redis_client(_settings())
        assert result is mock_client
