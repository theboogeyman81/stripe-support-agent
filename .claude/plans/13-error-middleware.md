# Plan 13 — Error Middleware

## Files created / modified
| File | Action |
|------|--------|
| `src/api/error_handlers.py` | Created — `register_error_handlers(app)` + async handler |
| `src/api/schemas.py` | Modified — added `ErrorResponse` model |
| `src/api/app.py` | Modified — imports and calls `register_error_handlers(app)` |
| `tests/test_error_handlers.py` | Created — 5 tests, no network calls |

## Key decisions
- Handler registered for base `Exception` only — FastAPI's built-in `HTTPException` and `RequestValidationError` handlers take precedence, so they are not intercepted.
- `logger.error("Unhandled exception", exc_info=exc)` — full traceback goes to the log, never to the response body.
- Tests use `TestClient(app, raise_server_exceptions=False)` to receive the 500 response rather than having the test itself raise.
- Test routes injected via `app.add_api_route()` after `create_app()` — no changes to production routes needed.

## Verification
```powershell
uv run python -c "from src.api.error_handlers import register_error_handlers; print('OK')"
uv run pytest tests/test_error_handlers.py -v
uv run pytest -v
uv run ruff check src/api/error_handlers.py src/api/schemas.py src/api/app.py
```
