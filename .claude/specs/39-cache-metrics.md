# Spec 39 — cache-metrics

## Feature
Track cache hit and miss counts for both the semantic cache and the exact-match
cache using Redis INCR counters, and expose them on a new `GET /metrics`
endpoint. Each `/ask` request increments the appropriate counter; the endpoint
reads all four counters and returns hits, misses, and hit rate per cache type.

## Why
Without counters we can't tell whether the caches are actually working —
whether the threshold is too tight, whether exact-match is redundant given
semantic, or whether caches are being bypassed silently. This endpoint gives
instant visibility without requiring Langfuse or any external dashboard.

## Input contract
- `src/api/routes/ask.py` — existing hit/miss decision points (semantic check
  before retrieve; `result["cache_hit"]` after generate).
- `src/cache/redis_client.py` — `redis_client` already on `app.state`.
- `src/api/app.py` — router registration.

## Output contract

### Counter keys in Redis
| Key | Incremented when |
|-----|-----------------|
| `metrics:semantic:hits` | `semantic_search` returns a result |
| `metrics:semantic:misses` | `semantic_search` returns None (cache was active) |
| `metrics:exact:hits` | `generate()` returns `cache_hit=True` |
| `metrics:exact:misses` | `generate()` returns `cache_hit=False` (cache was active) |

Counters have no TTL — they accumulate until the Redis instance is flushed.

### `GET /metrics` response shape
```json
{
  "semantic": {"hits": 5, "misses": 20, "hit_rate": 0.20},
  "exact":    {"hits": 3, "misses": 17, "hit_rate": 0.15},
  "total_requests": 25
}
```
`hit_rate` = hits / (hits + misses); 0.0 when both are zero.
`total_requests` = semantic hits + semantic misses (i.e., all `/ask` calls
that had Redis+embedder available; excludes calls with no cache active).
When Redis is unavailable, all values are 0.

### New files and changes
- `src/cache/metrics.py` — `increment()`, `get_metrics()`, counter key constants
- `src/api/routes/metrics.py` — `GET /metrics` route
- `src/api/schemas.py` — `CacheTypeMetrics`, `MetricsResponse`
- `src/api/app.py` — include metrics router
- `src/api/routes/ask.py` — call `increment()` at each hit/miss point
- `tests/test_cache_metrics.py` — unit tests for `src/cache/metrics.py`

## Scope (in)
- `src/cache/metrics.py` (new)
- `src/api/routes/metrics.py` (new)
- `src/api/schemas.py` — add `CacheTypeMetrics`, `MetricsResponse`
- `src/api/app.py` — register metrics router
- `src/api/routes/ask.py` — add `increment()` calls
- `tests/test_cache_metrics.py` (new)

## Scope (out)
- No Prometheus/OpenMetrics format — plain JSON only
- No per-session or per-user breakdown
- No counter reset endpoint
- No metrics for `/chat` (agent) endpoint
- No time-windowed rates (e.g., hits/minute) — feature 42 adds cost windows

## Dependencies
- New: none — Redis already installed; all counter logic uses `redis.incr` / `redis.get`
- Existing: `src/cache/redis_client.py`, `src/api/routes/ask.py`

## Acceptance criteria
1. `uv run ruff check src/cache/metrics.py src/api/routes/metrics.py src/api/schemas.py src/api/routes/ask.py tests/test_cache_metrics.py` — no errors.
2. `uv run pytest tests/test_cache_metrics.py -v` — all tests pass.
3. `uv run pytest -q` — full suite still passes.
4. With real Redis running, POST `/ask` three times (same question), then:
   `curl http://localhost:8000/metrics` returns semantic hits ≥ 2 and misses ≥ 1.
5. With `REDIS_URL=""`, `GET /metrics` returns `{"semantic": {"hits":0,"misses":0,"hit_rate":0.0}, "exact": {...}, "total_requests": 0}`.

## Failure modes to handle
- Redis unavailable at increment time: `increment()` catches `redis.RedisError`
  and no-ops — a counter write failure must never fail a `/ask` request.
- Redis unavailable at read time: `get_metrics()` returns all-zero dict.
- Counter key absent (never incremented): treat `redis.get()` returning None as 0.
- `redis_client` is None (no REDIS_URL): `increment()` no-ops; `get_metrics()`
  returns zeros immediately without touching Redis.

## Notes
- Only count exact-match metrics when `redis_client is not None` (i.e., when
  the exact-match cache was actually active). `result["cache_hit"]` is False
  even with no Redis, so we must gate on Redis presence.
- Only count semantic metrics when both `redis_client` and `embedder` are
  non-None (same gate as the semantic cache lookup in ask.py).
- `total_requests` is derived from semantic counters because semantic cache is
  checked on every request that has Redis+embedder active. If only Redis is
  present (no embedder), neither semantic counter increments — this is expected
  and the endpoint will show zeros for semantic while exact counters run.
