# Spec 40 — token-accounting

## Feature
Extend `LoggingMiddleware` to extract `input_tokens` and `output_tokens` from
successful `/ask` responses and (a) include them in the structured log line and
(b) accumulate running totals in Redis using atomic integer increments. Expose
the lifetime totals on the existing `GET /metrics` endpoint by adding a
`tokens` field to `MetricsResponse`.

## Why
`cost_usd` is already logged but tokens are not, making it impossible to
diagnose whether high cost comes from long prompts (input) or long answers
(output). Running totals in Redis give instant visibility — how many tokens
consumed so far, total spend — without needing Postgres queries. Feature 41
adds per-request Postgres records for windowed queries; this feature provides
the lightweight always-on counters.

## Input contract
- `src/api/middleware.py` — `LoggingMiddleware` already reads the response body
  and extracts `cost_usd` for `/ask` 200 responses. Extend the same block.
- `src/api/app.py` — `app.state.redis_client` is available on the request
  inside middleware via `request.app.state.redis_client`.
- `src/api/routes/metrics.py` — `GET /metrics` currently returns
  `MetricsResponse` with `semantic`, `exact`, and `total_requests`.

## Output contract

### Redis keys (no TTL — lifetime counters)
| Key | Operation | Stores |
|-----|-----------|--------|
| `stats:input_tokens` | `INCRBY` | cumulative prompt tokens (int) |
| `stats:output_tokens` | `INCRBY` | cumulative response tokens (int) |
| `stats:cost_micros` | `INCRBY` | cost_usd × 1 000 000 as int (avoids float drift) |
| `stats:requests` | `INCR` | total `/ask` requests that returned 200 |

### Middleware structured log line (extended)
```json
{
  "request_id": "...",
  "method": "POST",
  "path": "/ask",
  "status_code": 200,
  "latency_ms": 340.5,
  "cost_usd": 0.000312,
  "input_tokens": 1024,
  "output_tokens": 128
}
```
`input_tokens` and `output_tokens` are `null` for non-`/ask` paths or non-200
responses (same behaviour as `cost_usd` today).

### `GET /metrics` response (extended)
```json
{
  "semantic": {...},
  "exact": {...},
  "total_requests": 25,
  "tokens": {
    "total_input": 102400,
    "total_output": 12800,
    "total_cost_usd": 0.062,
    "total_requests": 50
  }
}
```
`tokens.total_requests` counts all 200 `/ask` responses (including cache hits
where `input_tokens` and `output_tokens` are 0 — but in practice the cached
response carries the original token counts, so they are non-zero).

### New/modified files
- `src/cache/token_stats.py` — `accumulate()`, `get_token_stats()`, key constants
- `src/api/middleware.py` — extract + log tokens; call `accumulate()`
- `src/api/schemas.py` — add `TokenStats`; extend `MetricsResponse` with `tokens`
- `src/api/routes/metrics.py` — call `get_token_stats()` and include in response
- `tests/test_token_stats.py` — unit tests

## Scope (in)
- `src/cache/token_stats.py` (new)
- `src/api/middleware.py` — extend body parsing block
- `src/api/schemas.py` — add `TokenStats`; add `tokens` field to `MetricsResponse`
- `src/api/routes/metrics.py` — include token stats
- `tests/test_token_stats.py` (new)

## Scope (out)
- No per-request Postgres storage (feature 41)
- No windowed queries (feature 42)
- No token tracking for `/chat` (agent) endpoint
- No per-model breakdown

## Dependencies
- New: none — `redis` already installed; all accumulation uses `INCR`/`INCRBY`
- Existing: `src/cache/metrics.py` (pattern to follow), `src/api/middleware.py`

## Acceptance criteria
1. `uv run ruff check src/cache/token_stats.py src/api/middleware.py src/api/schemas.py src/api/routes/metrics.py tests/test_token_stats.py` — no errors.
2. `uv run pytest tests/test_token_stats.py -v` — all tests pass.
3. `uv run pytest -q` — full suite still passes.
4. With real Redis running, POST `/ask` twice, then:
   `curl http://localhost:8000/metrics` returns `tokens.total_requests >= 2`
   and `tokens.total_input > 0`.
5. Logs show `"input_tokens"` and `"output_tokens"` fields in the JSON line
   for `/ask` requests.
6. With `REDIS_URL=""`, `/metrics` returns `tokens` with all zeros (no crash).

## Failure modes to handle
- Redis unavailable during `accumulate()`: catch `redis.RedisError`, no-op —
  a counter write must never fail an `/ask` request.
- `redis_client` is None: `accumulate()` no-ops immediately.
- Body parse error (non-JSON or missing keys): `input_tokens`/`output_tokens`
  fall back to None in the log; `accumulate()` is not called.
- `cost_usd` is a float — convert to micros via `int(round(cost_usd * 1_000_000))`
  before `INCRBY` to avoid integer overflow on very large values in tests.

## Notes
- Storing cost as integer micros (×10⁶) avoids Redis `INCRBYFLOAT` float
  drift across many increments. Divide by 1 000 000 on read.
- `accumulate()` is called from middleware, not from the route — middleware
  has already consumed the body and decoded the JSON, so there is no second
  body read.
- `tokens.total_requests` in the metrics response is independent of
  `total_requests` at the top level (which counts only requests with cache
  active). The two can differ when Redis is present but embedder is absent.
