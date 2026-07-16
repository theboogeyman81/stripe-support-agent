# Spec 07 — FastAPI Skeleton

## Feature
Create the `src/api/` package with a FastAPI app factory, wire `Settings` into
app state via an async lifespan, and provide a uvicorn entry point. No business
endpoints yet — those come in features 08–10. This skeleton is the foundation
every subsequent Phase 2 feature builds on.

## Why
Phase 1 exposed the RAG pipeline as a CLI. Phase 2 exposes it as an HTTP API.
Getting the app factory pattern right here means all later features just register
routers — they never touch app creation. A clean skeleton now prevents
architectural debt across six more features.

## Input contract
None. The app reads configuration from `src/config.py`'s `Settings` (loaded
from `.env`). `create_app()` optionally accepts a pre-built `Settings` instance
for testability.

## Output contract
- `uvicorn src.api.app:app` starts a server on `0.0.0.0:8000` (configurable via
  `api_host` / `api_port` in Settings).
- `GET /` returns HTTP 200 with JSON body:
  ```json
  {"status": "ok", "service": "stripe-support-agent", "version": "0.1.0"}
  ```
- After startup, `app.state.settings` holds a live `Settings` instance.

## Scope (in)
- `src/api/__init__.py` — empty package marker
- `src/api/app.py`:
  - `APP_VERSION = "0.1.0"` constant
  - `create_app(settings: Settings | None = None) -> FastAPI` — factory; uses
    `@asynccontextmanager` lifespan to store `settings or Settings()` in
    `app.state.settings`; registers `GET /`; sets
    `title="Stripe Support Agent"` and `version=APP_VERSION`
  - `app = create_app()` — module-level instance required by uvicorn
- `src/api/__main__.py` — `python -m src.api` entry point; reads `api_host` /
  `api_port` from `Settings()` and calls
  `uvicorn.run("src.api.app:app", host=..., port=..., reload=False)`
- `src/config.py` — add two fields:
  - `api_host: str = "0.0.0.0"`
  - `api_port: int = 8000`
- `tests/test_api_app.py`:
  - `test_create_app_returns_fastapi_instance` — `create_app()` returns a
    `FastAPI` object
  - `test_app_title_and_version` — `app.title == "Stripe Support Agent"` and
    `app.version == "0.1.0"`
  - `test_root_endpoint_returns_ok` — `GET /` via `TestClient` returns 200 and
    expected JSON keys
  - `test_app_state_has_settings_after_startup` — pass a mock `Settings`
    instance into `create_app(settings=mock_settings)`; use `TestClient` to
    drive lifespan; assert `app.state.settings is mock_settings`

## Scope (out)
- Any business endpoints (`/ask`, `/admin/ingest`, `/health`, `/ready`) —
  features 08–10
- Authentication / API-key gating — later features
- Structured JSON logging — feature 11
- Request-response Pydantic schemas — feature 12
- Error middleware — feature 13
- CORS configuration
- Docker / deployment wiring

## Dependencies
- New: `fastapi>=0.115`, `uvicorn[standard]>=0.30` — must be added to
  `pyproject.toml` via `uv add fastapi "uvicorn[standard]"` (human to approve
  before implementation)
- Existing: `pydantic-settings`, `httpx` (already in deps; used by
  `fastapi.testclient.TestClient`)

## Acceptance criteria
1. `uv add fastapi "uvicorn[standard]"` completes; both packages appear in
   `pyproject.toml`.
2. `uvicorn src.api.app:app --port 8000` starts without error and logs
   `Application startup complete.`
3. With the server running:
   `Invoke-WebRequest http://localhost:8000/ | Select-Object -ExpandProperty Content`
   returns `{"status":"ok","service":"stripe-support-agent","version":"0.1.0"}`.
4. `python -m src.api` starts the server on port 8000 (Ctrl-C to stop).
5. `uv run pytest tests/test_api_app.py` passes (4 tests, no network calls).
6. `uv run pytest` passes (all tests across all modules).
7. `uv run ruff check src/api/app.py src/api/__main__.py src/config.py` is
   clean.

## Failure modes to handle
- Missing env vars at startup (e.g. `GEMINI_API_KEY` not set): `Settings()`
  raises a pydantic `ValidationError` — let it propagate; the error message
  names the missing field clearly.
- Port already in use: let uvicorn raise `OSError`; no wrapping needed.

## Notes
- Use `@asynccontextmanager` lifespan (not the deprecated `@app.on_event`)
  — FastAPI ≥0.93 pattern. Signature:
  ```python
  from contextlib import asynccontextmanager

  @asynccontextmanager
  async def lifespan(app: FastAPI):
      app.state.settings = settings or Settings()
      yield
  ```
- `create_app()` itself must have no side effects at call time (no `Settings()`
  at module import). Side effects happen only when uvicorn starts the lifespan.
  `app = create_app()` at module level is safe because `create_app()` only
  constructs the `FastAPI` object — it does not call `Settings()`.
- For tests: pass a `Settings` instance constructed with dummy values directly
  to `create_app(settings=...)`. Use `with TestClient(app) as client:` (context
  manager form) to trigger lifespan in tests — this populates `app.state`.
- `uvicorn[standard]` includes `watchfiles` (needed for `--reload`) and
  `websockets`; the `[standard]` extra is the conventional install choice.
- `__main__.py` should NOT call `create_app()` itself — it uses the
  module-level `app` via the `"src.api.app:app"` string, which uvicorn imports.
