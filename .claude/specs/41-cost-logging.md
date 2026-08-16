# Spec 41 — cost-logging

## Feature
Write one row to a Postgres table (`request_costs`) for every successful `/ask`
response. Each row captures timestamp, token counts, estimated cost, cache hit
status, and model name. The table is created at startup if it does not exist.
Insertion is driven from `LoggingMiddleware`, which already parses the response
body for tokens and cost.

## Why
The Redis accumulators from feature 40 give lifetime totals, but they can't
answer "what did we spend in the last 7 days?" or "how many requests hit the
cache on Tuesday?". A Postgres row-per-request log makes time-windowed queries
trivial and gives feature 42 (`admin-cost-endpoint`) its data source.

## Input contract
- `src/api/middleware.py` — `LoggingMiddleware.dispatch()` already parses
  `cost_usd`, `input_tokens`, `output_tokens` from the `/ask` 200 body.
  This feature adds extraction of `cache_hit` from the same payload.
- `src/config.py` — `Settings.postgres_url` (already present, may be `""`).
- `src/db/tickets.py` — existing psycopg pattern to follow.
- `src/api/app.py` — lifespan is where `ensure_costs_table()` is called.

## Output contract

### Postgres table `request_costs`
```sql
CREATE TABLE IF NOT EXISTS request_costs (
    id            SERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    input_tokens  INT         NOT NULL,
    output_tokens INT         NOT NULL,
    cost_usd      NUMERIC(12, 8) NOT NULL,
    cache_hit     BOOLEAN     NOT NULL,
    model         TEXT        NOT NULL
)
```

### New and modified files
- `src/db/costs.py` — `ensure_costs_table(postgres_url)`, `insert_cost(...)`
- `src/api/app.py` — lifespan: call `ensure_costs_table()` if `postgres_url` set;
  store `postgres_url` on `app.state`
- `src/api/middleware.py` — extract `cache_hit` from body; call `insert_cost()`
  inside the existing `/ask` 200 branch (alongside `accumulate()`)
- `tests/test_cost_logging.py` — unit tests for `src/db/costs.py`, all mocked

## Scope (in)
- `src/db/costs.py` (new)
- `src/api/app.py` — add `ensure_costs_table()` call and `app.state.postgres_url`
- `src/api/middleware.py` — parse `cache_hit`; call `insert_cost()`
- `tests/test_cost_logging.py` (new)

## Scope (out)
- No changes to `src/db/tickets.py`.
- No admin endpoint — that is feature 42.
- No per-user or per-session cost breakdown.
- No cost logging for `/chat` (agent) endpoint.
- No migration tooling — `CREATE TABLE IF NOT EXISTS` is sufficient at demo scale.
- No async psycopg (`psycopg[async]`) — sync psycopg called from middleware is
  acceptable for a learning project.

## Dependencies
- New: none — `psycopg` is already installed (used by `src/db/tickets.py`).
- Existing: `src/db/tickets.py` (pattern reference), `src/config.py`,
  `src/api/middleware.py`, `src/api/app.py`.

## Acceptance criteria
1. `uv run ruff check src/db/costs.py src/api/app.py src/api/middleware.py tests/test_cost_logging.py` — no errors.
2. `uv run pytest tests/test_cost_logging.py -v` — all tests pass.
3. `uv run pytest -q` — full suite still passes.
4. With real Postgres configured, start the server and POST `/ask` once.
   `SELECT * FROM request_costs;` returns one row with correct token counts,
   `cost_usd > 0`, and `cache_hit = false`.
5. POST the same question again; the second row has `cache_hit = true` and
   `cost_usd = 0`.
6. With `POSTGRES_URL=""`, POST `/ask` succeeds and returns 200 (no insertion
   attempted, no error).

## Failure modes to handle
- `postgres_url` is `""`: `insert_cost()` checks for empty URL and returns
  immediately — no psycopg import errors or connection attempts.
- Postgres unreachable at startup: `ensure_costs_table()` is wrapped in
  try/except in the lifespan; a warning is printed but the app starts.
- Postgres unreachable at insert time: `insert_cost()` catches `Exception` and
  no-ops — a failed write must never fail a `/ask` request.
- `cache_hit` key absent from response body: treat as `False` (same
  try/except/else pattern already used for tokens).
- `app.state.postgres_url` absent (e.g. in tests): middleware uses
  `getattr(request.app.state, "postgres_url", "")` and skips insertion if empty.

## Notes
- `NUMERIC(12, 8)` stores cost_usd accurately without float drift; psycopg
  maps Python `float` to Postgres `NUMERIC` safely for our scale.
- Model name is not in the response body. Pass `"gemini-2.5-flash"` as a
  hardcoded default in `insert_cost()` — feature 42 does not filter by model,
  and we only use one model today.
- The lifespan already stores `app.state.redis_client` and `app.state.embedder`
  — store `app.state.postgres_url` (the raw URL string, not a connection) using
  the same pattern. A persistent connection pool is out of scope.
