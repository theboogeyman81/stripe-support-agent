"""Factory for the Redis cache client."""

import redis

from src.config import Settings


def get_redis_client(settings: Settings) -> redis.Redis:
    """Return a configured Redis client; raise ValueError if REDIS_URL is absent."""
    if not settings.redis_url:
        raise ValueError("REDIS_URL is not configured")
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        ssl_cert_reqs=None,  # Redis Cloud free tier uses self-signed certs
    )
