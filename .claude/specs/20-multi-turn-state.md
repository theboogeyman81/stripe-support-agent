# Spec 20 — Multi-Turn State

## Feature
Extend `run_agent()` in `src/agent/agent.py` to accept a prior conversation
history and return an updated history after each turn. This makes the agent
multi-turn capable: the caller holds the history, passes it back on each
request, and the agent can reference earlier turns ("as I mentioned before…",
"you said your email is…"). The API wiring lives in feature 21 (`chat-endpoint`);
this feature is purely the agent layer.

## Why
The phase-3 exit checklist requires "turn 2 references turn 1 correctly."
Without history, every call to `run_agent` starts a blank context — the agent
cannot remember the user's email from the previous turn, cannot follow up on a
ticket it just opened, and cannot correct itself based on clarifications. This
feature adds the plumbing; feature 21 exposes it via `POST /chat`.

## Input contract
- `src/agent/agent.py` — `run_agent` is the only function that changes
- `message_history` is passed in as `list[dict] | None` — JSON-serialisable
  dicts that the caller can store and send back. The agent layer converts
  to/from Pydantic AI's internal `ModelMessage` types.

## Output contract

### `src/agent/agent.py` (modify)

**New signature for `run_agent`:**
```python
def run_agent(
    question: str,
    settings: Settings,
    message_history: list[dict] | None = None,
) -> dict:
```

**New return shape** (adds `message_history` key):
```python
{
    "answer": str,
    "input_tokens": int,
    "output_tokens": int,
    "cost_usd": float,
    "message_history": list[dict],   # ← new
}
```

**Serialisation / deserialisation** using Pydantic AI's built-in adapter:
```python
from pydantic_ai.messages import ModelMessagesTypeAdapter

# deserialise incoming history (list[dict] → list[ModelMessage])
history = ModelMessagesTypeAdapter.validate_python(message_history) if message_history else None

# run with history
result = agent.run_sync(question, deps=settings, message_history=history)

# serialise outgoing history (list[ModelMessage] → list[dict])
"message_history": ModelMessagesTypeAdapter.dump_python(result.all_messages())
```

`ModelMessagesTypeAdapter` is `pydantic_ai.messages.ModelMessagesTypeAdapter`,
a `TypeAdapter[list[ModelMessage]]` provided by Pydantic AI — no custom code
needed.

### `tests/test_agent.py` (modify)
Add tests that verify:
1. `run_agent` returns a `message_history` key that is a non-empty list.
2. Passing `message_history` back on a second call does not raise.
3. `message_history=None` (first turn) still works — backwards-compatible.

All tests use `Agent("test")` mock — no live API calls.

## Scope (in)
- `src/agent/agent.py` — update `run_agent` signature and body
- `tests/test_agent.py` — add 3 tests for history behaviour

## Scope (out)
- No API endpoint changes (feature 21)
- No session ID or server-side history storage — caller holds state
- No trimming or truncation of long histories (Phase 4+)
- No changes to any tool, schema, or config file

## Dependencies
- New: none — `pydantic_ai.messages.ModelMessagesTypeAdapter` is already
  shipped with `pydantic-ai`
- Existing: `src/agent/agent.py`, `tests/test_agent.py`

## Acceptance criteria
1. `uv run ruff check src/agent/agent.py` exits 0.
2. `uv run pytest tests/test_agent.py -v` passes (all existing + new tests).
3. `message_history` key present in `run_agent` return value:
   ```powershell
   uv run python -c "
   from unittest.mock import patch
   from pydantic_ai import Agent
   from src.agent.agent import run_agent
   from src.config import Settings
   s = Settings(gemini_api_key='x', voyage_api_key='x', qdrant_url='http://localhost')
   with patch('src.agent.agent.create_agent', return_value=Agent('test', system_prompt='t')):
       r = run_agent('hello', s)
   assert 'message_history' in r, r.keys()
   assert isinstance(r['message_history'], list)
   print('OK')
   "
   ```
4. Two-turn round-trip (history from turn 1 passed into turn 2) does not raise:
   ```powershell
   uv run python -c "
   from unittest.mock import patch
   from pydantic_ai import Agent
   from src.agent.agent import run_agent
   from src.config import Settings
   s = Settings(gemini_api_key='x', voyage_api_key='x', qdrant_url='http://localhost')
   with patch('src.agent.agent.create_agent', return_value=Agent('test', system_prompt='t')):
       r1 = run_agent('hello', s)
       r2 = run_agent('follow up', s, message_history=r1['message_history'])
   print('OK', len(r2['message_history']), 'messages')
   "
   ```

## Failure modes to handle
- `message_history=None` (first turn): pass `None` to `run_sync` — Pydantic AI
  treats it as a blank context. No special handling needed.
- Malformed history dict: `ModelMessagesTypeAdapter.validate_python` will raise
  a `ValidationError` — let it propagate, the caller sent invalid data.

## Notes
- The caller (eventually the `/chat` endpoint in feature 21) is responsible for
  storing and re-sending history. The agent layer is stateless — it receives
  history, uses it, and returns the updated list.
- `result.all_messages()` includes both the incoming history and the new
  turn's messages, so the returned list is always the full cumulative history.
- `ModelMessagesTypeAdapter.dump_python()` returns plain Python dicts (not
  JSON strings), which FastAPI can serialise directly in feature 21.
