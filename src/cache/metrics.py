"""Redis-backed hit/miss counters for the exact-match and semantic caches."""

import redis

SEMANTIC_HITS   = "metrics:semantic:hits"
SEMANTIC_MISSES = "metrics:semantic:misses"
EXACT_HITS      = "metrics:exact:hits"
EXACT_MISSES    = "metrics:exact:misses"


def increment(redis_client: redis.Redis | None, key: str) -> None:
    """Increment a counter key; no-op if client is None or Redis errors."""
    if redis_client is None:
        return
    try:
        redis_client.incr(key)
    except Exception:
        pass


def _safe_int(redis_client: redis.Redis, key: str) -> int:
    val = redis_client.get(key)
    return int(val) if val is not None else 0


def _hit_rate(hits: int, misses: int) -> float:
    total = hits + misses
    return hits / total if total > 0 else 0.0


def get_metrics(redis_client: redis.Redis | None) -> dict:
    """Return hit/miss counts and rates; all zeros if Redis unavailable."""
    zero: dict = {"hits": 0, "misses": 0, "hit_rate": 0.0}
    if redis_client is None:
        return {"semantic": zero, "exact": zero, "total_requests": 0}
    try:
        sh = _safe_int(redis_client, SEMANTIC_HITS)
        sm = _safe_int(redis_client, SEMANTIC_MISSES)
        eh = _safe_int(redis_client, EXACT_HITS)
        em = _safe_int(redis_client, EXACT_MISSES)
        return {
            "semantic": {
                "hits": sh,
                "misses": sm,
                "hit_rate": _hit_rate(sh, sm),
            },
            "exact": {
                "hits": eh,
                "misses": em,
                "hit_rate": _hit_rate(eh, em),
            },
            "total_requests": sh + sm,
        }
    except Exception:
        return {"semantic": zero, "exact": zero, "total_requests": 0}
