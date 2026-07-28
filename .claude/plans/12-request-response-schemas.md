# Plan 12 — Request/Response Schemas

## Files created / modified
| File | Action |
|------|--------|
| `src/api/schemas.py` | Created — all nine Pydantic models with descriptions and examples |
| `src/api/routes/ask.py` | Modified — removed inline models, imports from schemas |
| `src/api/routes/ingest.py` | Modified — same |
| `src/api/routes/health.py` | Modified — same |
| `tests/test_schemas.py` | Created — 12 validation tests, no network calls |

## Key decisions
- All models in one flat `schemas.py` — too few to justify sub-modules.
- `SourceItem` and `ReadyCheck` get field descriptions but no `model_config` example (nested-only, never top-level).
- Route logic, decorators, and `response_model=` annotations are unchanged.
- Existing route tests continue to pass unchanged (they use `TestClient`, not direct model imports).

## Verification
```powershell
uv run python -c "from src.api.schemas import AskRequest, AskResponse, IngestRequest, IngestResponse, HealthResponse, ReadyResponse; print('OK')"
uv run pytest tests/test_schemas.py -v
uv run pytest -v
uv run ruff check src/api/schemas.py src/api/routes/ask.py src/api/routes/ingest.py src/api/routes/health.py
Select-String -Path "src/api/routes/*.py" -Pattern "class AskRequest|class AskResponse|class IngestRequest|class IngestResponse|class HealthResponse|class ReadyResponse|class SourceItem|class ReadyCheck"
```
