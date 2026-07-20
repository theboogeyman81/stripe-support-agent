# Spec 12 — Request/Response Schemas

## Feature
Centralise all Pydantic request and response models into a single
`src/api/schemas.py` module. Add field descriptions, validation constraints,
and `model_config` examples so the auto-generated OpenAPI docs at `/docs` are
self-explanatory. Update all route files to import from the new module instead
of defining models inline.

## Why
Schemas are currently defined ad-hoc inside each route file. As Phase 3 adds
more endpoints and Phase 4 adds observability, having a single authoritative
source of truth for the API contract prevents drift, makes the OpenAPI spec
richer (descriptions + examples appear in `/docs`), and lets tests import
schemas without importing route logic.

## Input contract
Existing inline Pydantic models in:
- `src/api/routes/ask.py` — `AskRequest`, `SourceItem`, `AskResponse`
- `src/api/routes/ingest.py` — `IngestRequest`, `IngestResponse`
- `src/api/routes/health.py` — `HealthResponse`, `ReadyCheck`, `ReadyResponse`

## Output contract
New file `src/api/schemas.py` exporting all nine models above with:
- `Field(description=...)` on every field
- `model_config = ConfigDict(json_schema_extra={"example": {...}})` on every
  request and response model (one realistic example per model)
- Validation constraints carried over from the existing inline definitions
  (e.g. `question` min_length=1, `top_k` ge=1)

Route files updated to `from src.api.schemas import ...` — no model definitions
remain in route files.

## Scope (in)
- Create `src/api/schemas.py`
- Update `src/api/routes/ask.py`, `src/api/routes/ingest.py`,
  `src/api/routes/health.py` to import from `src/api/schemas`
- Add `tests/test_schemas.py` covering field validation

## Scope (out)
- No changes to route logic, middleware, or app factory
- No new endpoints
- No versioning (`/v1/` prefix) — that is Phase 3+
- No response envelope wrapping (e.g. `{"data": ..., "error": null}`) — that
  is feature 13's concern

## Dependencies
- New: none
- Existing: `pydantic` (already in `pyproject.toml`)

## Acceptance criteria
1. `uv run python -c "from src.api.schemas import AskRequest, AskResponse, IngestRequest, IngestResponse, HealthResponse, ReadyResponse"` exits 0.
2. `uv run pytest tests/test_schemas.py -v` passes.
3. `uv run uvicorn src.api.app:app --port 8000` then `curl http://localhost:8000/docs` returns HTML containing `"AskRequest"` and `"IngestResponse"` in the OpenAPI spec.
4. `uv run ruff check src/api/schemas.py src/api/routes/ask.py src/api/routes/ingest.py src/api/routes/health.py` exits 0.
5. `grep -r "class AskRequest\|class AskResponse\|class IngestRequest\|class IngestResponse\|class HealthResponse\|class ReadyResponse" src/api/routes/` returns no matches (models no longer defined in route files).

## Failure modes to handle
- Missing field on `AskRequest` (no `question`): Pydantic raises `ValidationError`; FastAPI returns 422 automatically — no extra handling needed, but the test should assert the 422 shape.
- `top_k` below 1: same 422 path — assert constraint is enforced.

## Notes
- Keep all nine models in one flat file (`schemas.py`). Do not split into
  sub-modules — there are too few models to justify it yet.
- `SourceItem` does not need a `model_config` example since it is a nested
  component, not a top-level request/response.
- The `ReadyCheck` nested model similarly needs no standalone example.
- Do not add `response_model_exclude_none=True` to routes — that changes
  serialisation behaviour and belongs in a separate decision.
