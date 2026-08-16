# Spec 36 — redis-setup

## Feature
Add Redis as a dependency: configure the connection via `Settings`, expose a
`get_redis_client()` factory in `src/cache/redis_client.py`, add
`REDIS_URL` to `.env.example`, extend `GET /health` to report Redis
connectivity, and wire a startup/shutdown lifespan check into the FastAPI app.

## Why
Features 37–38 (exact-match and semantic caches) need a tested, config-driven
Redis connection before they can be built. This feature installs `redis[hiredis]`,
defines where the URL comes from, and proves the connection works end-to-end
via the health endpoint.

No Docker is available on this machine. We will use **Redis Cloud free tier**
(30 MB, no credit card) instead of a local container, the same pattern we
followed for Qdrant Cloud.

## Input contract
- `.env` — must contain `REDIS_URL=rediss://<user>:<password>@<host>:<port>`
  (Redis Cloud free tier uses TLS, scheme is `rediss://`).

## Output contract
- `src/cache/__init__.py` — empty init
- `src/cache/redis_client.py` — exports `get_redis_client(settings: Settings) -> redis.Redis`
- `src/config.py` — new `redis_url: str = ""` field
- `.env.example` — new `REDIS_URL=rediss://...` line
- `src/api/app.py` — lifespan pings Redis on startup; logs warning (not crash) if unreachable
- `src/api/routes/health.py` — `GET /health` response gains `"redis": "ok" | "error: <msg>"`
- `src/api/schemas.py` — `HealthResponse` gains optional `redis` field
- `tests/test_redis_client.py` — unit tests, Redis client mocked

## Scope (in)
- `src/cache/__init__.py` and `src/cache/redis_client.py`
- `src/config.py` — add `redis_url`
- `.env.example` — add `REDIS_URL`
- `src/api/app.py` — startup ping via lifespan
- `src/api/routes/health.py` — Redis status in response
- `src/api/schemas.py` — `HealthResponse.redis` field
- `tests/test_redis_client.py`

## Scope (out)
- No caching logic (feature 37+)
- No Lua scripts, pub/sub, streams
- No Redis Sentinel or Cluster config

## Dependencies
- New: `redis[hiredis]>=5.0` (approved stack, Phase 6)
- Existing: `pydantic-settings`, `fastapi`, `src/config.py`

## Acceptance criteria
1. `uv run ruff check src/cache/ src/api/app.py src/api/routes/health.py src/api/schemas.py tests/test_redis_client.py` — no errors.
2. `uv run pytest tests/test_redis_client.py -v` — all tests pass.
3. With a valid `REDIS_URL` in `.env`:
   `uv run uvicorn src.api.app:app --reload` starts, logs confirm Redis ping succeeded.
4. `curl http://localhost:8000/health` returns `{"status":"ok","redis":"ok", ...}`.
5. With `REDIS_URL=""` in `.env`:
   app starts (no crash), health returns `{"status":"ok","redis":"error: ...", ...}`.

## Failure modes to handle
- `REDIS_URL` empty or missing: `get_redis_client` raises `ValueError` with a clear message; startup lifespan catches it, logs a warning, and continues (graceful degradation).
- Connection timeout / auth failure: `ping()` raises `redis.RedisError`; lifespan catches and logs; health endpoint reports `"error: <msg>"`.
- TLS cert errors on `rediss://`: pass `ssl_cert_reqs=None` to skip verification (Redis Cloud free tier uses self-signed-ish certs in some regions).

## Notes
- `get_redis_client` should be a plain factory function (not a singleton), so tests can call it with a mock `Settings` object without global state.
- `decode_responses=True` so values come back as `str`, not `bytes` — consistent with how features 37–38 will use it.
- Redis Cloud free tier URL format: `rediss://default:<password>@<host>:<port>`.
