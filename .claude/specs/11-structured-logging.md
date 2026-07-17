# Spec 11 — Structured Logging

## Feature
Add a FastAPI middleware that emits one JSON log line per request containing:
`request_id`, `method`, `path`, `status_code`, `latency_ms`, and `cost_usd`.
The `request_id` is a UUID generated per request and attached to the response
as an `X-Request-ID` header. `cost_usd` is extracted from the `POST /ask`
response body when available; it is `null` for all other routes.

## Why
Plain uvicorn access logs are unstructured text — hard to query, impossible to
correlate across requests, and useless for cost tracking. One JSON line per
request gives us a machine-readable audit trail that later phases (Langfuse,
dashboards, cost alerts) can consume without any schema migration. The
`request_id` also gives us a handle to correlate a client error report with a
specific server log line.

## Input contract
No new API inputs. The middleware intercepts every HTTP request automatically.

## Output contract
For every request the server handles, one JSON line is written to stderr via
Python's `logging` module at `INFO` level:

```json
{
  "request_id": "b3d2c1a0-...",
  "method": "POST",
  "path": "/ask",
  "status_code": 200,
  "latency_ms": 1423.7,
  "cost_usd": 0.000741
}
```

Field rules:
- `request_id`: UUID4 string, unique per request.
- `method`: HTTP method string, uppercase (`"GET"`, `"POST"`, …).
- `path`: URL path only, no query string (`"/ask"`, `"/health"`, …).
- `status_code`: integer HTTP status code.
- `latency_ms`: float, wall-clock milliseconds from request received to
  response sent, rounded to one decimal place.
- `cost_usd`: float from the `/ask` response body when the route is `POST /ask`
  and the response is 200; `null` for all other routes and for non-200 `/ask`
  responses.

Additionally, every response carries the header:
```
X-Request-ID: <same UUID as in the log line>
```

## Scope (in)
- `src/api/middleware.py` — new file:
  - `LoggingMiddleware(BaseHTTPMiddleware)` from `starlette.middleware.base`:
    - Generates a `request_id = str(uuid.uuid4())` at the start of each request.
    - Records `start = time.perf_counter()` before calling `await call_next(request)`.
    - After the response, computes `latency_ms = round((time.perf_counter() - start) * 1000, 1)`.
    - Extracts `cost_usd`: only for `POST /ask` with `status_code == 200` —
      reads `response.body` and parses it as JSON to get `cost_usd`; otherwise `None`.
    - Emits one `logger.info(json.dumps({...}))` call with all 6 fields.
    - Adds `X-Request-ID` header to the response before returning it.
- `src/api/app.py` — add middleware in `create_app()`:
  `app.add_middleware(LoggingMiddleware)` after the router registrations.
- `src/api/__main__.py` — configure root logger to emit JSON-friendly output:
  `logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)`
  so log lines are bare JSON with no prefix noise.
- `tests/test_middleware.py` — new file:
  - `test_logging_middleware_emits_json_log_on_ask`
  - `test_logging_middleware_cost_usd_null_for_health`
  - `test_logging_middleware_x_request_id_header_present`
  - `test_logging_middleware_status_code_logged_correctly`

## Scope (out)
- Per-request logging inside individual route handlers
- Logging request/response bodies beyond `cost_usd`
- Propagating `request_id` into downstream AI calls (Phase 4 Langfuse)
- Async middleware (sticking with sync-compatible `BaseHTTPMiddleware`)
- Log rotation, file sinks, or third-party log libraries (structlog, loguru)
- Filtering health-endpoint noise from logs

## Dependencies
- New: none — `starlette.middleware.base.BaseHTTPMiddleware` is already
  available via `fastapi`; `uuid`, `time`, `json`, `logging` are stdlib.
- Existing: `src/api/app.py`, `src/api/__main__.py`

## Acceptance criteria
1. With the server running (`uvicorn src.api.app:app --port 8000`), send a
   question and observe stderr:
   ```powershell
   Invoke-WebRequest -Uri http://localhost:8000/ask `
     -Method POST `
     -ContentType "application/json" `
     -Body '{"question": "What is a webhook?"}' | Out-Null
   ```
   The server's stderr contains a JSON line with all 6 fields and
   `cost_usd` is a non-null float.
2. `GET http://localhost:8000/health` produces a log line with
   `"path": "/health"` and `"cost_usd": null`.
3. Every response includes an `X-Request-ID` header:
   ```powershell
   (Invoke-WebRequest -Uri http://localhost:8000/health).Headers["X-Request-ID"]
   ```
   Prints a UUID string.
4. `uv run pytest tests/test_middleware.py` passes (4 tests, no network calls).
5. `uv run pytest` passes (all tests).
6. `uv run ruff check src/api/middleware.py src/api/app.py src/api/__main__.py` is clean.

## Failure modes to handle
- `/ask` returns non-200 (502, 422): log the status code, set `cost_usd` to `null`.
- Response body is not valid JSON (shouldn't happen, but defensive): set
  `cost_usd` to `null`, do not raise.
- Any exception inside the middleware itself: must not swallow the original
  response — catch internally, log a warning, still return the response.

## Notes
- `BaseHTTPMiddleware` buffers the response body, so reading `response.body`
  after `await call_next(request)` is safe. The response must be converted to a
  `Response` object first: wrap the result of `call_next` with
  `response = Response(content=await call_next(request).body, ...)` — actually
  the correct pattern is:
  ```python
  from starlette.responses import Response
  response = await call_next(request)
  body = b""
  async for chunk in response.body_iterator:
      body += chunk
  # parse body, then rebuild:
  return Response(content=body, status_code=response.status_code,
                  headers=dict(response.headers), media_type=response.media_type)
  ```
  This is needed because streaming responses consume their iterator; rebuilding
  ensures downstream consumers (TestClient, real clients) still get the body.
- In tests, use `caplog` (pytest's log capture fixture) to assert the emitted
  JSON line. Alternatively, mock `logger.info` and assert it was called with
  a JSON string containing the expected keys.
- The `logger` in `middleware.py` should be module-level:
  `logger = logging.getLogger(__name__)` — this gives log lines the name
  `src.api.middleware` in any log aggregator.
- `__main__.py` already exists — check its contents before editing; only add
  the `basicConfig` call if it isn't already there.
- `cost_usd` extraction: `json.loads(body)["cost_usd"]` — wrap in
  `try/except (json.JSONDecodeError, KeyError)` and fall back to `None`.
