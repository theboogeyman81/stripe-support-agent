# Spec 21 — Chat Endpoint

## Feature
Add a `POST /chat` endpoint that exposes the Pydantic AI agent over HTTP with
multi-turn conversation support. The client sends a question and an optional
`session_id`; the server looks up the stored history for that session, calls
`run_agent`, saves the updated history, and returns the answer. Sessions are
stored in an in-memory dict on the server — no Redis yet (Phase 6). This is the
last feature in Phase 3 and completes the agent's public surface.

## Why
Features 14–20 built the agent and all its capabilities entirely in Python.
This feature makes the agent reachable over HTTP so the frontend (Phase 7) and
evaluation harness (Phase 5) can call it. It also closes the Phase 3 exit
checklist item: "multi-turn: turn 2 references turn 1 correctly" — the
session_id is what allows this across separate HTTP requests.

## Input contract
- `src/agent/agent.py` — `run_agent(question, settings, message_history)` from
  feature 20
- `src/api/app.py` — existing app factory where the new router is registered
- `src/api/schemas.py` — where new Pydantic models are added
- No new infrastructure — history is a plain `dict` in process memory

## Output contract

### `src/api/schemas.py` (modify)
Add two new models:

```python
class ChatRequest(BaseModel):
    session_id: str | None = Field(
        default=None,
        description="Conversation session id; omit to start a new session",
    )
    question: str = Field(min_length=1, description="User's message")

class ChatResponse(BaseModel):
    session_id: str = Field(description="Session id to pass back on the next turn")
    answer: str = Field(description="Agent's response")
    input_tokens: int
    output_tokens: int
    cost_usd: float
```

### `src/api/routes/chat.py` (new)
One route and one module-level session store:

```python
_sessions: dict[str, list[dict]] = {}
```

`POST /chat` logic:
1. If `request.session_id` is `None` or not in `_sessions`, generate a new
   `uuid.uuid4()` string as the session id and initialise `_sessions[sid] = []`.
2. Look up `history = _sessions[sid]`.
3. Call `result = run_agent(request.question, settings, message_history=history)`.
4. Update `_sessions[sid] = result["message_history"]`.
5. Return `ChatResponse(session_id=sid, answer=result["answer"], ...)`.

Settings are read from `request.app.state.settings` (same pattern as the
`/ask` route uses implicitly via the lifespan).

### `src/api/app.py` (modify)
Register the new chat router:
```python
from src.api.routes import chat as chat_routes
app.include_router(chat_routes.router)
```

### `tests/test_chat_route.py` (new)
Use FastAPI's `TestClient`. Mock `run_agent` at `src.api.routes.chat.run_agent`.

## Scope (in)
- `src/api/schemas.py` — add `ChatRequest`, `ChatResponse`
- `src/api/routes/chat.py` — new route file with `_sessions` store
- `src/api/app.py` — register chat router
- `tests/test_chat_route.py` — new test file

## Scope (out)
- No session TTL or expiry (Phase 6+)
- No persistent session storage — in-memory only (Phase 6+)
- No endpoint to list or delete sessions
- No streaming response (Phase 4+)
- No changes to `/ask`, `/admin/ingest`, or health routes
- No changes to `run_agent` — feature 20 already handles history

## Dependencies
- New: none — `uuid` is stdlib
- Existing: `src.agent.agent.run_agent`, `src.api.schemas`, `fastapi.testclient`

## Acceptance criteria
1. `uv run ruff check src/api/routes/chat.py src/api/schemas.py src/api/app.py` exits 0.
2. `uv run pytest tests/test_chat_route.py -v` passes.
3. First turn starts a new session:
   ```powershell
   uv run uvicorn src.api.app:app --port 8000 &
   curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d "{\"question\": \"What is a PaymentIntent?\"}" | python -m json.tool
   ```
   Response contains `session_id` (a UUID string) and `answer`.
4. Second turn using the returned `session_id` continues the conversation:
   ```powershell
   curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d "{\"session_id\": \"<id from above>\", \"question\": \"Tell me more\"}" | python -m json.tool
   ```
   Returns an answer that contextually follows the first.

## Failure modes to handle
- Empty question: FastAPI validates `min_length=1` on `ChatRequest.question`
  and returns 422 automatically — no extra handling needed.
- `run_agent` raises (e.g. Gemini unreachable): catch `Exception` and raise
  `HTTPException(status_code=502, detail=f"upstream error: {e}")` — same
  pattern as the `/ask` route.
- Unknown `session_id` sent by client: treat as a new session (reinitialise
  history to `[]`) — more forgiving than a 404.

## Notes
- `_sessions` is a module-level dict — it resets on process restart, which is
  fine for Phase 3 dev. Redis replaces it in Phase 6.
- Settings are accessed via `request.app.state.settings` inside the route
  function. The lifespan in `app.py` sets `app.state.settings` at startup.
- Tests must inject settings via `TestClient(create_app(settings=...))` so
  the lifespan fires with known keys — the same pattern used in existing
  route tests.
