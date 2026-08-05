# Spec 13 — Error Middleware

## Feature
Add a global exception handler to the FastAPI app that catches any unhandled
`Exception`, logs it server-side with the full traceback, and returns a
uniform JSON error body without leaking the traceback or internal detail to
the caller. Also add an `ErrorResponse` Pydantic model to `src/api/schemas.py`
so the error shape appears in the OpenAPI spec at `/docs`.

## Why
Currently, unhandled exceptions surface as FastAPI's default 500 response which
includes the exception string in the body. Routes that raise `HTTPException`
already return `{"detail": "..."}` but the shape is implicit. This feature
makes the error contract explicit and safe: callers always get
`{"detail": "..."}` with a safe message, the server log always has the full
traceback, and `/docs` documents the error model.

## Input contract
Existing files consumed:
- `src/api/app.py` — app factory where the handler is registered
- `src/api/schemas.py` — where `ErrorResponse` is added
- `src/api/middleware.py` — existing `LoggingMiddleware` (read-only reference)

## Output contract

### `src/api/schemas.py` — add one model
```python
class ErrorResponse(BaseModel):
    detail: str  # human-readable error message, never a traceback
```
With `model_config` example `{"detail": "internal server error"}`.

### `src/api/error_handlers.py` — new file
One function: `register_error_handlers(app: FastAPI) -> None`

Registers a single handler for the base `Exception` type:
- Logs `ERROR` level with `exc_info=True` (full traceback goes to the log)
- Returns `JSONResponse(status_code=500, content={"detail": "internal server error"})`

Does **not** intercept `HTTPException` or `RequestValidationError` — FastAPI's
built-in handling for those is correct and already returns `{"detail": ...}`.

### `src/api/app.py` — wire it in
Call `register_error_handlers(app)` inside `create_app()`, after middleware is
added.

## Scope (in)
- `src/api/schemas.py` — add `ErrorResponse`
- `src/api/error_handlers.py` — create with `register_error_handlers`
- `src/api/app.py` — call `register_error_handlers(app)`
- `tests/test_error_handlers.py` — new test file

## Scope (out)
- No changes to route logic or existing `HTTPException` raises
- No request-ID injection into error bodies (that is a Phase 4 concern)
- No custom handling of 404 / 405 — FastAPI defaults are fine
- No wrapping of `RequestValidationError` — the 422 shape FastAPI produces
  is standard and already correct
- No rate-limiting or circuit-breaker logic

## Dependencies
- New: none
- Existing: `fastapi`, `starlette` (already present)

## Acceptance criteria
1. `uv run python -c "from src.api.error_handlers import register_error_handlers; print('OK')"` exits 0.
2. `uv run pytest tests/test_error_handlers.py -v` passes.
3. `uv run pytest -v` passes (no regressions).
4. `uv run ruff check src/api/error_handlers.py src/api/schemas.py src/api/app.py` exits 0.
5. A route that raises an unhandled `RuntimeError` returns HTTP 500 with body
   `{"detail": "internal server error"}` and does NOT include the exception
   message or traceback in the response body.

## Failure modes to handle
- Unhandled `Exception` in any route: return 500 `{"detail": "internal server error"}`, log traceback.
- `HTTPException` raised explicitly by routes (e.g. 401, 403, 502): FastAPI handles these — do not intercept.
- Pydantic `RequestValidationError` (422): FastAPI handles these — do not intercept.

## Notes
- FastAPI registers exception handlers via `app.add_exception_handler(ExcType, handler)`.
  The handler signature is `async def handler(request: Request, exc: Exception) -> Response`.
- Registering a handler for the base `Exception` does NOT override FastAPI's
  built-in `HTTPException` and `RequestValidationError` handlers — FastAPI
  checks more-specific handlers first.
- The `ErrorResponse` model should be referenced as `responses={500: {"model": ErrorResponse}}`
  in the route decorator if we want it to appear per-endpoint in OpenAPI — but
  that is optional and out of scope here. Adding it to `schemas.py` is enough
  for now.
