# Spec 42 — admin-cost-endpoint

## Feature
Add `GET /admin/costs?window=7d` — an admin-gated endpoint that queries the
`request_costs` table from feature 41 and returns aggregate spend and request
counts for a configurable lookback window. The window is expressed as `Nd`
(e.g. `1d`, `7d`, `30d`). The endpoint is protected by the existing
`X-Admin-Key` header guard from `src/api/routes/ingest.py`.

## Why
Feature 41 logs every request cost row but provides no way to query them. This
endpoint closes the loop: the phase-6 exit checklist requires `/admin/costs`
to show accurate 7-day spend. It also validates that the Postgres schema is
actually being written to correctly.

## Input contract
- Query parameter `window` — string matching `\d+d` (e.g. `7d`). Default `7d`.
  Reject anything that doesn't match with HTTP 422.
- Header `X-Admin-Key` — must equal `settings.admin_api_key`. Reuse the
  `_check_admin_key` dependency from `src/api/routes/ingest.py` (move it to a
  shared location so both routes can import it).
- `app.state.postgres_url` — set by feature 41 lifespan; may be `""`.
- `request_costs` table — columns: `created_at`, `input_tokens`,
  `output_tokens`, `cost_usd`, `cache_hit`, `model`.

## Output contract

### `GET /admin/costs?window=7d` response (200)
```json
{
  "window": "7d",
  "total_requests": 42,
  "cache_hits": 18,
  "total_input_tokens": 84000,
  "total_output_tokens": 8400,
  "total_cost_usd": 0.03528
}
```

Field rules:
- `window` — echoed back from the query parameter.
- `total_requests` — COUNT(*) of rows where `created_at >= NOW() - INTERVAL`.
- `cache_hits` — COUNT(*) filtered by `cache_hit = TRUE` in the same window.
- `total_input_tokens` — SUM(input_tokens) in the window; 0 if no rows.
- `total_output_tokens` — SUM(output_tokens) in the window; 0 if no rows.
- `total_cost_usd` — SUM(cost_usd) cast to float; 0.0 if no rows.

When `postgres_url` is `""` or Postgres is unreachable, return all-zero
values (same graceful-degradation pattern as Redis endpoints).

### New and modified files
- `src/db/costs.py` — add `query_costs(postgres_url, days)` function.
- `src/api/routes/costs.py` — new route file, `GET /admin/costs`.
- `src/api/routes/ingest.py` — extract `_check_admin_key` to shared module.
- `src/api/deps.py` — new shared module holding `check_admin_key` dependency.
- `src/api/schemas.py` — add `CostsResponse`.
- `src/api/app.py` — register costs router.
- `tests/test_admin_costs.py` — unit tests, all mocked.

## Scope (in)
- `src/db/costs.py` — add `query_costs()`
- `src/api/deps.py` (new) — `check_admin_key` FastAPI dependency
- `src/api/routes/ingest.py` — replace inline `_check_admin_key` with import from `deps`
- `src/api/routes/costs.py` (new) — `GET /admin/costs` route
- `src/api/schemas.py` — add `CostsResponse`
- `src/api/app.py` — register costs router
- `tests/test_admin_costs.py` (new)

## Scope (out)
- No breakdown by model, session, or user.
- No hourly or minute-level granularity — days only.
- No pagination or cursor.
- No CSV/export format — JSON only.
- No window formats other than `Nd` (no `7h`, `1w`, ISO 8601).
- No changes to the `request_costs` schema.

## Dependencies
- New: none — `psycopg` already installed.
- Existing: `src/db/costs.py`, `src/api/routes/ingest.py`,
  `src/api/schemas.py`, `src/api/app.py`.

## Acceptance criteria
1. `uv run ruff check src/db/costs.py src/api/deps.py src/api/routes/costs.py src/api/routes/ingest.py src/api/schemas.py src/api/app.py tests/test_admin_costs.py` — no errors.
2. `uv run pytest tests/test_admin_costs.py -v` — all tests pass.
3. `uv run pytest -q` — full suite still passes.
4. With real Postgres, start the server, POST `/ask` twice, then:
   `curl -H "X-Admin-Key: changeme" "http://localhost:8000/admin/costs?window=7d"`
   returns `total_requests: 2` and `total_cost_usd > 0`.
5. `curl -H "X-Admin-Key: changeme" "http://localhost:8000/admin/costs?window=1d"`
   also returns 200 with correct counts.
6. `curl "http://localhost:8000/admin/costs?window=7d"` (no key) → 401.
7. `curl -H "X-Admin-Key: changeme" "http://localhost:8000/admin/costs?window=abc"` → 422.
8. With `POSTGRES_URL=""`, endpoint returns 200 with all-zero values.

## Failure modes to handle
- `postgres_url` is `""`: `query_costs()` returns the all-zero dict immediately.
- Postgres unreachable at query time: `query_costs()` catches `Exception` and
  returns all-zero dict — a DB outage must never return 5xx.
- `window` param fails regex: FastAPI validator raises 422 before the handler runs.
- SUM returns NULL (no rows in window): coerce to 0 / 0.0 in Python.
- Missing `X-Admin-Key`: 401. Wrong key: 403. Both handled by `check_admin_key`.

## Notes
- The `_check_admin_key` function in `ingest.py` is currently module-private
  (underscore prefix). Moving it to `src/api/deps.py` as `check_admin_key`
  (no underscore) lets both routes share it without duplication. Update
  `ingest.py` to import from `deps`.
- Window parsing: split on `d` — `int("7d".rstrip("d"))` → 7. Use a regex
  validator on the query param: `pattern=r"^\d+d$"` via `Query(pattern=...)`.
- Postgres `INTERVAL` syntax: `NOW() - INTERVAL '7 days'` — pass the integer
  days as a Python f-string into the SQL string (not as a psycopg parameter,
  since `%s` can't bind an INTERVAL literal). Days is an integer parsed from
  the validated window string, so there is no injection risk.
