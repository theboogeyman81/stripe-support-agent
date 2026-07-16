# Spec 08 — Ask Endpoint

## Feature
Add `POST /ask` to the FastAPI app. It accepts a question and optional `top_k`,
calls the Phase 1 `retrieve()` and `generate()` functions in sequence, and
returns a typed JSON response with the answer, deduplicated sources, token
counts, and cost. No new AI logic — this is pure wiring.

## Why
Feature 07 gave us a running FastAPI app with no business routes. This feature
exposes the core RAG capability over HTTP, making the agent usable by any
client (frontend, Postman, curl) rather than just the CLI.

## Input contract
`POST /ask` — JSON body:
```json
{
  "question": "How do I create a refund?",
  "top_k": 5
}
```
- `question`: required, non-empty string (min length 1)
- `top_k`: optional integer, default `5`, minimum `1`

## Output contract
HTTP 200 — JSON body:
```json
{
  "answer": "To create a refund...",
  "sources": [
    {"title": "Refunds", "url": "https://docs.stripe.com/refunds"},
    {"title": "Disputes", "url": "https://docs.stripe.com/disputes"}
  ],
  "input_tokens": 1234,
  "output_tokens": 256,
  "cost_usd": 0.000741
}
```
- `answer`: non-empty string from `generate()`
- `sources`: list of `{title, url}` objects, **deduplicated by URL**, preserving
  first-seen order from the retrieved chunks
- `input_tokens` / `output_tokens`: ints from `generate()`
- `cost_usd`: float from `generate()`

HTTP 422 — FastAPI/Pydantic validation error (blank question, `top_k < 1`):
```json
{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}
```

HTTP 502 — upstream AI/vector failure (Gemini or Voyage/Qdrant raises):
```json
{"detail": "upstream error: <exception message>"}
```

## Scope (in)
- `src/api/routes/__init__.py` — empty package marker
- `src/api/routes/ask.py`:
  - `AskRequest(BaseModel)` — `question: str` with `min_length=1`,
    `top_k: int = 5` with `ge=1`
  - `SourceItem(BaseModel)` — `title: str`, `url: str`
  - `AskResponse(BaseModel)` — `answer: str`, `sources: list[SourceItem]`,
    `input_tokens: int`, `output_tokens: int`, `cost_usd: float`
  - `router = APIRouter()` with `POST /ask` handler:
    - Calls `retrieve(request.question, request.top_k)`
    - Deduplicates sources by URL (preserve order)
    - Calls `generate(request.question, chunks)`
    - On any exception from `retrieve` or `generate`: catches and raises
      `HTTPException(status_code=502, detail=f"upstream error: {e}")`
    - Returns `AskResponse`
- `src/api/app.py` — register the ask router:
  `app.include_router(ask_router)` inside `create_app()`
- `tests/test_ask_route.py`:
  - `test_ask_returns_200_with_expected_shape`
  - `test_ask_empty_question_returns_422`
  - `test_ask_top_k_default_is_five`
  - `test_ask_sources_deduplicated_by_url`
  - `test_ask_upstream_error_returns_502`

## Scope (out)
- Authentication / API-key gating on this endpoint (feature 09's admin gate)
- Structured JSON logging with request IDs (feature 11)
- Moving schemas to a shared `src/api/schemas.py` (feature 12)
- Re-ranking retrieved chunks (later phase)
- Streaming responses (later phase)
- Rate limiting

## Dependencies
- New: none
- Existing: `src/rag/vectorstore.retrieve`, `src/rag/generator.generate`,
  `src/api/app.py`, `fastapi`, `pydantic`

## Acceptance criteria
1. With the server running (`uvicorn src.api.app:app --port 8000`):
   ```powershell
   Invoke-WebRequest -Uri http://localhost:8000/ask `
     -Method POST `
     -ContentType "application/json" `
     -Body '{"question": "How do I create a refund?"}' |
     Select-Object -ExpandProperty Content
   ```
   Returns JSON with a non-empty `answer`, at least one entry in `sources`,
   and a `cost_usd` greater than 0.
2. Sending `{"question": ""}` returns HTTP 422.
3. Sending `{"question": "test", "top_k": 0}` returns HTTP 422.
4. Sending `{"question": "What is webhook signing?"}` returns HTTP 200 with
   `sources` containing no duplicate URLs.
5. `uv run pytest tests/test_ask_route.py` passes (5 tests, no network calls).
6. `uv run pytest` passes (all tests).
7. `uv run ruff check src/api/routes/ask.py src/api/app.py` is clean.

## Failure modes to handle
- `retrieve()` raises (Qdrant unreachable, Voyage error, empty query): catch
  all exceptions, return 502 with `"upstream error: <message>"`
- `generate()` raises (Gemini API error, empty chunks): same — catch and 502
- `question` is blank/whitespace: Pydantic `min_length=1` catches this and
  returns 422 before the handler runs
- `top_k < 1`: Pydantic `ge=1` catches this and returns 422

## Notes
- Import `retrieve` and `generate` at the top of `routes/ask.py` as module-level
  imports — this makes them trivially patchable in tests with
  `patch("src.api.routes.ask.retrieve", ...)`.
- Source deduplication: iterate retrieved chunks in order, add to a list only
  if the URL hasn't been seen yet. Use a `set` to track seen URLs. Do not sort.
- Pydantic v2 constraint syntax: `question: str = Field(min_length=1)` and
  `top_k: int = Field(default=5, ge=1)`. Import `Field` from `pydantic`.
- In tests, mock both `retrieve` and `generate` at the route module level.
  The mock for `retrieve` returns a list of dicts matching the shape from
  `vectorstore.search()` (keys: `chunk_id`, `score`, `doc_url`, `doc_title`,
  `text`, `chunk_index`). The mock for `generate` returns a dict with keys
  `answer`, `input_tokens`, `output_tokens`, `cost_usd`.
- `app.include_router(ask_router)` goes inside `create_app()` after the `GET /`
  route, not at module level — preserves the no-side-effects-at-import rule.
- Feature 12 will extract `AskRequest`, `SourceItem`, `AskResponse` to a shared
  `src/api/schemas.py`; placing them in `routes/ask.py` for now is intentional
  and scoped.
