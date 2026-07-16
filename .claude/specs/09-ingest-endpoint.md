# Spec 09 — Ingest Endpoint

## Feature
Add `POST /admin/ingest` to the FastAPI app. It triggers the full ingestion
pipeline (load → chunk → embed → upsert) and returns statistics about what was
done. The endpoint is gated behind an `X-Admin-Key` header checked against a
secret stored in settings. The pipeline logic is extracted from `ingest.py`
into a reusable `run_ingest()` function so both the CLI and the API share the
same code path.

## Why
The CLI ingest is a one-shot tool — fine for initial setup but not for
programmatic or automated re-ingestion. Exposing it as an HTTP endpoint lets
any client (cron job, CI pipeline, admin UI) trigger a re-ingest without shell
access. The refactor of `ingest.py` also removes the `sys.exit` / `argparse`
coupling from the core logic, making it testable in isolation.

## Input contract
`POST /admin/ingest` — requires header:
```
X-Admin-Key: <value matching settings.admin_api_key>
```

Optional JSON body (all fields optional, body itself may be omitted):
```json
{
  "recreate": false
}
```
- `recreate`: boolean, default `false`. When `true`, drops and recreates the
  Qdrant collection before upserting (mirrors `--recreate` CLI flag). When
  `false`, skips already-cached steps (docs, chunks, embeddings) and only
  upserts new data.

## Output contract
HTTP 200 — JSON body:
```json
{
  "docs_loaded": 412,
  "chunks_produced": 4319,
  "vectors_embedded": 4319,
  "vectors_skipped": 0,
  "points_upserted": 4319,
  "embed_cost_usd": 0.0302,
  "cached_steps": ["docs", "chunks"]
}
```
- `docs_loaded`: int — number of documents loaded (0 if step was skipped)
- `chunks_produced`: int — number of chunks produced (0 if step was skipped)
- `vectors_embedded`: int — number of vectors newly embedded this run
- `vectors_skipped`: int — number of vectors skipped because embeddings already existed
- `points_upserted`: int — number of points upserted into Qdrant
- `embed_cost_usd`: float — cost of embedding this run (0.0 if embeddings were cached)
- `cached_steps`: list[str] — which steps were skipped because cached data existed;
  values from `{"docs", "chunks", "embeddings"}`

HTTP 401 — missing `X-Admin-Key` header:
```json
{"detail": "missing admin key"}
```

HTTP 403 — wrong key value:
```json
{"detail": "invalid admin key"}
```

HTTP 502 — any exception from the pipeline (network, Qdrant, Voyage, Gemini):
```json
{"detail": "ingest error: <exception message>"}
```

## Scope (in)
- `src/ingest.py` — extract `run_ingest(settings: Settings, recreate: bool = False) -> dict`
  that contains all pipeline logic currently in `main()`. `main()` becomes a
  thin wrapper that parses args and calls `run_ingest()`. No `sys.exit` inside
  `run_ingest()` — raise `RuntimeError` instead for missing files.
- `src/api/routes/ingest.py` — new file:
  - `IngestRequest(BaseModel)` — `recreate: bool = False`
  - `IngestResponse(BaseModel)` — all fields from output contract above
  - `_check_admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"))` —
    FastAPI dependency; raises `HTTPException(401)` if header absent, `HTTPException(403)`
    if value doesn't match `settings.admin_api_key`
  - `router = APIRouter(prefix="/admin")` with `POST /ingest` handler:
    - Depends on `_check_admin_key`
    - Calls `run_ingest(settings, request.recreate)`
    - On exception: catches and raises `HTTPException(status_code=502, detail=f"ingest error: {e}")`
    - Returns `IngestResponse`
- `src/api/app.py` — register ingest router:
  `app.include_router(ingest_routes.router)` inside `create_app()`
- `src/config.py` — add `admin_api_key: str = "changeme"` to `Settings`
- `tests/test_ingest_route.py`:
  - `test_ingest_missing_key_returns_401`
  - `test_ingest_wrong_key_returns_403`
  - `test_ingest_valid_key_returns_200_with_expected_shape`
  - `test_ingest_pipeline_error_returns_502`
  - `test_ingest_recreate_flag_passed_through`

## Scope (out)
- Background / async execution (ingest is synchronous, blocks the request)
- Progress streaming or server-sent events
- Per-step retry logic
- Rate limiting or concurrent ingest prevention
- Moving `IngestRequest` / `IngestResponse` to shared `src/api/schemas.py` (feature 12)
- Any change to how chunks, embeddings, or docs are stored on disk

## Dependencies
- New: none
- Existing: `src/ingest.run_ingest`, `src/config.Settings`,
  `src/api/app.py`, `fastapi`, `pydantic`

## Acceptance criteria
1. With the server running (`uvicorn src.api.app:app --port 8000`) and
   `ADMIN_API_KEY=secret` set in `.env`:
   ```powershell
   Invoke-WebRequest -Uri http://localhost:8000/admin/ingest `
     -Method POST `
     -ContentType "application/json" `
     -Headers @{"X-Admin-Key" = "secret"} `
     -Body '{}' |
     Select-Object -ExpandProperty Content
   ```
   Returns HTTP 200 with JSON containing integer `points_upserted` > 0.
2. Omitting the `X-Admin-Key` header returns HTTP 401 with
   `{"detail": "missing admin key"}`.
3. Sending `X-Admin-Key: wrongvalue` returns HTTP 403 with
   `{"detail": "invalid admin key"}`.
4. `uv run pytest tests/test_ingest_route.py` passes (5 tests, no network calls).
5. `uv run pytest` passes (all tests).
6. `uv run ruff check src/ingest.py src/api/routes/ingest.py src/api/app.py src/config.py` is clean.
7. The CLI still works after the refactor:
   ```powershell
   uv run python -m src.ingest --help
   ```
   Prints usage without error.

## Failure modes to handle
- Missing `X-Admin-Key` header: 401 with `"missing admin key"`
- Wrong `X-Admin-Key` value: 403 with `"invalid admin key"`
- `run_ingest()` raises `RuntimeError` (missing data files): catch in route,
  return 502 with `"ingest error: <message>"`
- Any network error from Qdrant, Voyage, or Gemini during pipeline: same — 502
- `admin_api_key` not set in `.env`: the `Settings` default is `"changeme"`;
  document in `.env.example` that this must be overridden in production

## Notes
- The `_check_admin_key` dependency reads `settings.admin_api_key` via
  `app.state.settings` injected in the lifespan. To access app state in a
  FastAPI dependency, use `Request` as a parameter:
  `def _check_admin_key(request: Request, x_admin_key: ...)`.
- In tests, mock `run_ingest` at the route module level:
  `patch("src.api.routes.ingest.run_ingest", ...)`. The mock returns a plain
  dict matching the output contract. Set `admin_api_key="test-key"` in the
  test `Settings` override so auth checks pass without real credentials.
- `run_ingest()` must return a dict with all 7 keys even when steps are
  skipped — zero-fill skipped numeric fields, add the step name to
  `cached_steps`.
- The `Header(alias="X-Admin-Key")` annotation is required because FastAPI
  normalises header names to lowercase; the alias preserves the conventional
  capitalisation in docs while still matching the actual HTTP header.
- `admin_api_key` should be added to `.env.example` with value `changeme` and
  a comment warning to change it before any real deployment.
