# Spec 27 — Session Grouping

## Feature
Thread the `/chat` session ID through `run_agent()` into the Langfuse trace so
that all turns of a single conversation are grouped under one Langfuse session.
Today each agent turn produces an isolated trace with no link to the turns before
or after it. After this feature, opening a session in the Langfuse UI shows
every turn of that conversation in order.

## Why
Features 24–26 produce individual traces and spans. Without session grouping,
you cannot tell in Langfuse which traces belong to the same conversation thread.
The `/chat` endpoint already has a stable `session_id` UUID (used for multi-turn
message history in feature 21). Passing it to Langfuse costs one extra argument
and unlocks the full session-replay view: see the full conversation flow,
cumulative cost, and which tool calls happened across turns.

## Input contract
- `src/agent/agent.py` — `run_agent()` and the Langfuse `start_observation`
  call added in feature 24
- `src/api/routes/chat.py` — the `sid` UUID already in scope when calling
  `run_agent()`
- Langfuse SDK v4 (`langfuse==4.14.3`) — `start_observation` must support
  a way to attach a session ID to the root span (direct parameter or
  `metadata`)

## Output contract

### `src/agent/agent.py` (modify)

`run_agent()` gains a new optional parameter:

```python
def run_agent(
    question: str,
    settings: Settings,
    message_history: list[dict] | None = None,
    session_id: str | None = None,
) -> dict:
```

Inside the tracing block, pass `session_id` when opening the root span.
Check which form the Langfuse v4 SDK accepts during planning; use whichever
is available, in this order of preference:

1. Direct kwarg: `client.start_observation(..., session_id=session_id)`
2. Via metadata: `client.start_observation(..., metadata={"session_id": session_id})`

If `session_id is None`, omit it (do not pass `session_id=None` explicitly —
let the default apply so single-turn calls from `/ask` or the CLI produce clean
traces without a null session).

### `src/api/routes/chat.py` (modify)

Pass `session_id=sid` when calling `run_agent()`:

```python
result = run_agent(body.question, settings, message_history=history, session_id=sid)
```

No other changes to the route.

### `tests/test_agent.py` (modify)

Two new tests:

| Test | Setup | Expected |
|------|-------|---------|
| `test_run_agent_passes_session_id_to_langfuse` | mock `create_agent` + mock `get_langfuse_client`; call `run_agent(..., session_id="test-sid")` | `client.start_observation` called with `session_id="test-sid"` (or it appears in `metadata`) |
| `test_run_agent_omits_session_id_when_none` | mock `create_agent` + mock `get_langfuse_client`; call `run_agent(...)` without `session_id` | `client.start_observation` called without `session_id` kwarg (or `session_id` not in `metadata`) |

### `tests/test_chat.py` (modify, if it exists) or verify manually
Confirm the `/chat` route passes `session_id` to `run_agent`. If `test_chat.py`
exists, add one assertion; otherwise verify via the live smoke test.

## Scope (in)
- `src/agent/agent.py` — add `session_id` parameter, forward to Langfuse span
- `src/api/routes/chat.py` — pass `session_id=sid` to `run_agent()`
- `tests/test_agent.py` — 2 new tests

## Scope (out)
- Grouping tool spans or retrieval spans under the session — those are sibling
  observations and would require OTel context propagation; deferred
- Flushing on app shutdown — not blocking for this feature; Langfuse SDK
  registers atexit handlers automatically
- Storing or exposing session IDs in the database — Postgres ticket records
  do not need a session_id column for now
- Any changes to `/ask`, CLI, ingest, or config

## Dependencies
- New: none
- Existing: `src/agent/agent.run_agent`, `src/api/routes/chat`

## Acceptance criteria
1. `uv run pytest tests/test_agent.py -v` passes (all existing + 2 new).
2. `uv run ruff check src/agent/agent.py src/api/routes/chat.py` exits 0.
3. `uv run pytest -q` — full suite passes with no regressions.
4. Live smoke test — send two questions in the same `/chat` session, open
   Langfuse UI → Sessions, confirm both traces appear under one session ID.

## Failure modes to handle
- `session_id` is `None` (stateless callers): omit from `start_observation`
  call — trace appears without a session in Langfuse, which is correct.
- Langfuse client absent (keys missing): existing `if client:` guard skips all
  tracing — `session_id` param is ignored, no crash.

## Notes
- The `sid` in `chat.py` is a UUID string already used as the multi-turn
  history key. Reusing it as the Langfuse session ID means the Langfuse session
  and the server-side history both share the same identifier.
- During planning, verify the exact Langfuse v4 parameter by inspecting
  `.venv/Lib/site-packages/langfuse/_client/client.py` for `start_observation`
  signature or any `session_id`-related parameter/attribute setter.
