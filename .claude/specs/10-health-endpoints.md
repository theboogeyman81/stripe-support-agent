# Spec 10 — Health Endpoints

## Feature
Add two health-check routes to the FastAPI app:
- `GET /health` — liveness probe: confirms the process is running and the app
  started correctly. Always returns 200 as long as the server is up.
- `GET /ready` — readiness probe: confirms external dependencies (Qdrant) are
  reachable. Returns 200 if Qdrant responds, 503 if it does not.

## Why
Without health endpoints, there is no programmatic way to tell whether the
service is alive or whether its dependencies are up. These two endpoints are the
standard pattern used by Docker, Kubernetes, and load balancers to gate traffic
and restart unhealthy containers. They also give us a fast sanity-check when
starting the server locally.

## Input contract
Both endpoints accept `GET` with no body and no query parameters.

## Output contract

### `GET /health` — always 200
```json
{
  "status": "ok"
}
```

### `GET /ready` — 200 when Qdrant is reachable
```json
{
  "status": "ok",
  "checks": {
    "qdrant": "ok"
  }
}
```

### `GET /ready` — 503 when Qdrant is unreachable
```json
{
  "status": "degraded",
  "checks": {
    "qdrant": "unreachable"
  }
}
```
- `status`: `"ok"` if all checks pass, `"degraded"` if any fail.
- `checks.qdrant`: `"ok"` if `QdrantStore.ping()` succeeds, `"unreachable"` if
  it raises any exception.

## Scope (in)
- `src/rag/vectorstore.py` — add a `ping(self) -> bool` method to `QdrantStore`:
  - Calls `self.client.get_collections()` (a lightweight Qdrant API call).
  - Returns `True` on success, raises the underlying exception on failure.
- `src/api/routes/health.py` — new file:
  - `HealthResponse(BaseModel)` — `status: str`
  - `ReadyCheck(BaseModel)` — `qdrant: str`
  - `ReadyResponse(BaseModel)` — `status: str`, `checks: ReadyCheck`
  - `router = APIRouter()` with:
    - `GET /health` handler: returns `HealthResponse(status="ok")` unconditionally.
    - `GET /ready` handler:
      - Reads `settings` from `request.app.state.settings`.
      - Instantiates `QdrantStore` using settings.
      - Calls `store.ping()`.
      - On success: returns `ReadyResponse(status="ok", checks=ReadyCheck(qdrant="ok"))`.
      - On any exception: returns `JSONResponse(status_code=503, ...)` with
        `status="degraded"` and `checks.qdrant="unreachable"`.
- `src/api/app.py` — register health router:
  `app.include_router(health_routes.router)` inside `create_app()`.
- `tests/test_health_routes.py`:
  - `test_health_returns_200_with_ok_status`
  - `test_ready_returns_200_when_qdrant_reachable`
  - `test_ready_returns_503_when_qdrant_unreachable`
- `tests/test_vectorstore.py` — add one test:
  - `test_ping_returns_true_when_client_succeeds`
  - `test_ping_raises_when_client_fails`

## Scope (out)
- Checking any dependency other than Qdrant (Voyage, Gemini, Redis)
- Auth-gating health endpoints (they must be open for infrastructure probes)
- Detailed latency or metrics in the response body
- Moving schemas to shared `src/api/schemas.py` (feature 12)
- Caching the readiness result

## Dependencies
- New: none
- Existing: `src/rag/vectorstore.QdrantStore`, `src/api/app.py`, `src/config.Settings`,
  `fastapi`, `pydantic`

## Acceptance criteria
1. With the server running (`uvicorn src.api.app:app --port 8000`):
   ```powershell
   Invoke-WebRequest -Uri http://localhost:8000/health -Method GET |
     Select-Object -ExpandProperty Content
   ```
   Returns HTTP 200 with `{"status":"ok"}`.
2. With Qdrant reachable:
   ```powershell
   Invoke-WebRequest -Uri http://localhost:8000/ready -Method GET |
     Select-Object -ExpandProperty Content
   ```
   Returns HTTP 200 with `{"status":"ok","checks":{"qdrant":"ok"}}`.
3. With Qdrant unreachable (e.g. wrong `QDRANT_URL` in `.env`):
   ```powershell
   Invoke-WebRequest -Uri http://localhost:8000/ready -Method GET `
     -ErrorAction SilentlyContinue |
     Select-Object -ExpandProperty StatusCode
   ```
   Returns HTTP 503.
4. `uv run pytest tests/test_health_routes.py` passes (3 tests, no network calls).
5. `uv run pytest` passes (all tests).
6. `uv run ruff check src/rag/vectorstore.py src/api/routes/health.py src/api/app.py` is clean.

## Failure modes to handle
- Qdrant connection refused, timeout, or wrong URL: `ping()` raises → `/ready`
  returns 503 with `"unreachable"`.
- `settings.qdrant_url` or `settings.qdrant_api_key` missing/blank: `QdrantStore`
  init raises → same 503 path.
- `/health` must never return non-200, regardless of dependency state.

## Notes
- `GET /health` intentionally has no dependency on any external service. It is
  purely a liveness signal — "the process is running."
- `/ready` must return a `JSONResponse` with `status_code=503` (not raise
  `HTTPException`) so the body is still JSON and parseable by probes.
- `ping()` uses `self.client.get_collections()` because it is the lightest
  Qdrant call that requires a real network round-trip — it does not depend on
  the collection existing yet.
- In tests, mock `QdrantStore` at the route module level:
  `patch("src.api.routes.health.QdrantStore", ...)`. Configure the mock's
  `ping()` to return `True` or raise `Exception("down")` as needed.
- In the `test_vectorstore.py` additions, mock `self.client.get_collections`
  directly on a constructed `QdrantStore` instance — do not make real network
  calls.
- Feature 12 will extract `HealthResponse`, `ReadyCheck`, `ReadyResponse` to
  `src/api/schemas.py`; placing them in `routes/health.py` for now is
  intentional.
