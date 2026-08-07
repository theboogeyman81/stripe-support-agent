# Spec 23 — Langfuse SDK Integration

## Feature
Add the `langfuse` Python SDK as a dependency and create a
`src/observability/` package with a single `get_langfuse_client()` function
that returns a configured `Langfuse` client (or `None` if credentials are
absent). Features 24–28 import this function to create traces — none of them
should touch client initialisation directly. This feature is the SDK wiring
only; no actual tracing yet.

## Why
Features 24–28 all need a ready-to-use `Langfuse` client. Centralising
initialisation in one place means credentials are validated once, the
`LANGFUSE_HOST` setting is honoured consistently, and graceful degradation
(missing keys → `None`) is handled in a single location rather than repeated
across every tracing callsite. Feature 22 added the credentials to `Settings`;
this feature adds the SDK and the factory that uses them.

## Input contract
- `src/config.py` — `Settings.langfuse_public_key`, `langfuse_secret_key`,
  `langfuse_host` from feature 22
- New dependency: `langfuse` — **must be approved before adding to
  `pyproject.toml`**

## Output contract

### `pyproject.toml` (modify)
Add `"langfuse"` to the `dependencies` list.

### `src/observability/__init__.py` (new)
Empty — makes `src.observability` a package.

### `src/observability/langfuse_client.py` (new)

```python
from langfuse import Langfuse
from src.config import Settings

def get_langfuse_client(settings: Settings) -> Langfuse | None:
    """Return a configured Langfuse client, or None if credentials are absent."""
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
```

- Returns `None` when either key is empty — callers must guard with
  `if client:` before using it. This means the app runs fine without
  Langfuse configured (dev/test environments).
- No side effects at import time — `Langfuse(...)` is called inside the
  function, not at module level.
- No connection is made at construction time; the SDK connects lazily on
  first trace.

### `tests/test_langfuse_client.py` (new)
Mock `langfuse.Langfuse` at the import boundary. Three tests:

| Test | Setup | Expected |
|------|-------|---------|
| `test_returns_client_when_keys_present` | settings with both keys set | returns a `Langfuse` instance |
| `test_returns_none_when_public_key_missing` | `langfuse_public_key=""` | returns `None` |
| `test_returns_none_when_secret_key_missing` | `langfuse_secret_key=""` | returns `None` |
| `test_passes_correct_args_to_langfuse` | settings with keys and custom host | `Langfuse(...)` called with exact key/host values |

## Scope (in)
- `pyproject.toml` — add `langfuse` dependency
- `src/observability/__init__.py` — new, empty
- `src/observability/langfuse_client.py` — new, one public function
- `tests/test_langfuse_client.py` — new, 4 tests

## Scope (out)
- No tracing of any calls — features 24–28
- No middleware or FastAPI lifespan integration — feature 24+
- No flush/shutdown handling — feature 27+
- No changes to agent, tools, routes, or config

## Dependencies
- New: `langfuse` — approved required before implementation
- Existing: `src/config.Settings`

## Acceptance criteria
1. `uv run python -c "from src.observability.langfuse_client import get_langfuse_client; print('OK')"` exits 0.
2. `uv run pytest tests/test_langfuse_client.py -v` passes (all 4 tests, Langfuse constructor mocked).
3. `uv run ruff check src/observability/langfuse_client.py` exits 0.
4. Live smoke test (requires keys in `.env`):
   ```powershell
   uv run python -c "
   from src.config import Settings
   from src.observability.langfuse_client import get_langfuse_client
   client = get_langfuse_client(Settings())
   print('client ready:', client is not None)
   "
   ```
   Prints `client ready: True`.

## Failure modes to handle
- Missing keys: return `None` — callers skip tracing gracefully.
- Wrong host or bad keys: `Langfuse(...)` constructs without error (lazy
  connection); the failure surfaces on first trace call in features 24+.
  Let it propagate there.

## Notes
- `langfuse` SDK version: use whatever `uv add langfuse` resolves to —
  the free-tier API is stable.
- The `Langfuse` constructor does not validate credentials at init time,
  so mocking it in tests is straightforward — just check it was called
  with the right args.
- Callers in features 24–28 will always do `client = get_langfuse_client(settings); if client: ...`
  so `None` propagates safely without any extra error handling.
