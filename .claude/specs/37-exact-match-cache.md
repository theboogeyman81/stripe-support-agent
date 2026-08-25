# Spec 37 — exact-match-cache

## Feature
Add an exact-match cache layer in front of `generate()` in
`src/rag/generator.py`. Before calling Gemini, hash the full rendered prompt
(model name + prompt text) and check Redis. On a hit, return the cached
result immediately at zero LLM cost. On a miss, call Gemini as normal and
write the result to Redis before returning.

## Why
Identical questions (same wording, same retrieved chunks) hit Gemini every
time today. An exact-match cache eliminates redundant LLM spend for repeated
queries — the most common case in a support agent. This also demonstrates the
simplest caching pattern before the harder semantic case in feature 38.

## Input contract
- `src/cache/redis_client.py` — `get_redis_client(settings)` factory (feature 36).
- `src/config.py` — `Settings` with `redis_url`, `cache_ttl_seconds` (new field, default 3600).
- `src/rag/generator.py` — `build_prompt()` and `generate()` already exist.

## Output contract
- `src/cache/exact_match.py` — exports two functions:
  - `cache_key(model: str, prompt: str) -> str`
    Returns `"exact:<sha256hex>"` — deterministic, collision-resistant.
  - `get_cached(redis_client: redis.Redis, key: str) -> dict | None`
    Returns parsed JSON dict on hit, `None` on miss or Redis error.
  - `set_cached(redis_client: redis.Redis, key: str, value: dict, ttl: int) -> None`
    Writes JSON-serialised `value` with TTL; silently swallows Redis errors.
- `src/rag/generator.py` — `generate()` gains two optional parameters:
  - `redis_client: redis.Redis | None = None`
  - `cache_ttl: int = 3600`
  When `redis_client` is provided, attempts cache lookup before Gemini and
  writes on miss. Cache hit adds `"cache_hit": True` to the returned dict;
  miss adds `"cache_hit": False`.
- `src/api/routes/ask.py` — passes `redis_client` and `cache_ttl` from
  `app.state` into `generate()`.
- `src/api/schemas.py` — `AskResponse` gains `cache_hit: bool = False`.
- `src/config.py` — new `cache_ttl_seconds: int = 3600` field.
- `.env.example` — new `CACHE_TTL_SECONDS=3600` line.
- `tests/test_exact_match.py` — unit tests for `src/cache/exact_match.py`.
- `tests/test_generator.py` — existing tests must still pass; new tests cover
  cache-hit and cache-miss paths.

## Scope (in)
- `src/cache/exact_match.py` (new)
- `src/config.py` — add `cache_ttl_seconds`
- `.env.example` — add `CACHE_TTL_SECONDS`
- `src/rag/generator.py` — modify `generate()`
- `src/api/routes/ask.py` — pass Redis client into `generate()`
- `src/api/app.py` — store `redis_client` on `app.state` at startup
- `src/api/schemas.py` — add `cache_hit` field to `AskResponse`
- `tests/test_exact_match.py` (new)
- `tests/test_generator.py` (modify — add cache path tests)

## Scope (out)
- No semantic/embedding-based cache (feature 38)
- No cache invalidation endpoint
- No per-user or per-session cache namespacing
- No cache for the `/chat` (agent) endpoint — only `/ask`
- No cache metrics or hit-rate counters (feature 39)

## Dependencies
- New: none (redis already added in feature 36)
- Existing: `redis[hiredis]`, `src/cache/redis_client.py`, `src/config.py`

## Acceptance criteria
1. `uv run ruff check src/cache/exact_match.py src/rag/generator.py src/api/routes/ask.py src/api/schemas.py tests/test_exact_match.py tests/test_generator.py` — no errors.
2. `uv run pytest tests/test_exact_match.py tests/test_generator.py -v` — all pass.
3. `uv run pytest -q` — full suite still passes.
4. With a real `REDIS_URL` in `.env`, start the server and POST the same question twice:
   - First response: `"cache_hit": false`
   - Second response: `"cache_hit": true` (faster, zero LLM cost)
5. With `REDIS_URL=""` in `.env`, the endpoint still returns answers (cache silently disabled).

## Failure modes to handle
- Redis unavailable at request time: `get_cached` / `set_cached` catch
  `redis.RedisError` and return `None` / no-op respectively — Gemini is
  always called as the fallback.
- `redis_client` is `None` (REDIS_URL not set): skip cache entirely, behave
  as today.
- Corrupt cached value (invalid JSON): treat as miss, call Gemini.

## Notes
- Cache key must include the model name so a model upgrade automatically
  invalidates all entries.
- `set_cached` must never raise — a Redis write failure must not fail a
  user-facing request.
- Store the Redis client on `app.state` at startup (reuse the ping client
  from feature 36 lifespan) rather than constructing a new one per request.
