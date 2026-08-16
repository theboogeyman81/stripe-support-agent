"""Exact-match cache helpers: key generation, get, and set."""

import hashlib
import json

import redis


def cache_key(model: str, prompt: str) -> str:
    """Return 'exact:<sha256>' of model+prompt — deterministic cache key."""
    digest = hashlib.sha256(f"{model}\n{prompt}".encode()).hexdigest()
    return f"exact:{digest}"


def get_cached(redis_client: redis.Redis, key: str) -> dict | None:
    """Return parsed cached dict, or None on miss, Redis error, or bad JSON."""
    try:
        raw = redis_client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None


def set_cached(
    redis_client: redis.Redis, key: str, value: dict, ttl: int
) -> None:
    """Write value to Redis with TTL; silently swallow any error."""
    try:
        storable = {k: v for k, v in value.items() if k != "cache_hit"}
        redis_client.setex(key, ttl, json.dumps(storable))
    except Exception:
        pass
