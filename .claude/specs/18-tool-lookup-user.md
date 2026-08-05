# Spec 18 — Tool: Lookup User

## Feature
Add a `lookup_user` Pydantic AI tool that retrieves a mock user record by email
address from an in-memory fixture store. When a user says "my account email is
x@example.com" or the agent needs to personalise a response, it calls this tool
to get the user's name, plan tier, and account status. No real database — a
hardcoded Python dict of seeded fixtures is sufficient for Phase 3.

## Why
The phase-3 exit checklist requires the agent to handle account-level questions
and personalise responses. `lookup_user` gives the agent a way to retrieve user
context so it can say "Your account is on the Starter plan" rather than a
generic answer. Feature 19 (`agent-system-prompt`) will instruct the agent
when to call this tool. No new infrastructure is needed — all data is in-process.

## Input contract
- `src/agent/tools.py` — where the tool function lives
- `src/agent/agent.py` — where the tool is registered
- No new files, no database, no network

## Output contract

### `src/agent/tools.py` (modify)
Add one new public tool function:

```python
def lookup_user(ctx: RunContext[Settings], email: str) -> str:
    """Look up a mock user by email and return their account details."""
```

- Strips and lowercases the email before lookup.
- Returns a formatted string on success:
  ```
  User: Jane Smith
  Email: jane@example.com
  Plan: Pro
  Status: active
  ```
- Returns `f"No user found for email: {email}."` if not in the fixture store.
- Raises `ValueError("email must not be empty")` if the email is blank.

### `src/agent/fixtures.py` (new)
A single module-level dict of seeded mock users. No side effects at import time
(it is just a literal dict). No I/O.

```python
MOCK_USERS: dict[str, dict] = {
    "alice@example.com": {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "plan": "Starter",
        "status": "active",
    },
    "bob@example.com": {
        "name": "Bob Martinez",
        "email": "bob@example.com",
        "plan": "Pro",
        "status": "active",
    },
    "carol@example.com": {
        "name": "Carol Chen",
        "email": "carol@example.com",
        "plan": "Enterprise",
        "status": "suspended",
    },
}
```

Keys are lowercase email strings. At least 3 fixtures — one per plan tier, one
with a non-active status to exercise the suspended path.

### Changes to `src/agent/agent.py`
- Add `lookup_user` to `tools=[...]` in `create_agent()`. No other changes.

## Scope (in)
- `src/agent/fixtures.py` — new, mock user dict
- `src/agent/tools.py` — add `lookup_user` tool
- `src/agent/agent.py` — add `lookup_user` to `tools=[]`
- `tests/test_tools.py` — add tests for `lookup_user`

## Scope (out)
- No real user database or Postgres table (Phase 4+)
- No user creation, update, or deletion
- No authentication or session linking
- No fuzzy email matching — exact match only (case-insensitive)
- No changes to any API routes or config

## Dependencies
- New: none
- Existing: `pydantic_ai.RunContext`, `src.config.Settings`

## Acceptance criteria
1. `uv run python -c "from src.agent.tools import lookup_user; print('OK')"` exits 0.
2. `uv run python -c "from src.agent.fixtures import MOCK_USERS; print(len(MOCK_USERS))"` prints `3` (or more).
3. `uv run pytest tests/test_tools.py -v` passes (all new tests included).
4. `uv run ruff check src/agent/fixtures.py src/agent/tools.py src/agent/agent.py` exits 0.
5. Manual spot check (no API cost):
   ```powershell
   uv run python -c "
   from unittest.mock import MagicMock
   from src.agent.tools import lookup_user
   ctx = MagicMock()
   ctx.deps = MagicMock()
   print(lookup_user(ctx, 'alice@example.com'))
   print(lookup_user(ctx, 'UNKNOWN@example.com'))
   "
   ```
   First call prints the Alice fixture. Second prints the not-found message.

## Failure modes to handle
- Empty email: raise `ValueError("email must not be empty")`.
- Unknown email: return `f"No user found for email: {email}."` — not an exception, so the agent can relay the message gracefully.
- Mixed-case email (e.g. `Alice@Example.COM`): normalise to lowercase before lookup.

## Notes
- `MOCK_USERS` lives in `src/agent/fixtures.py`, not inline in `tools.py`, so
  tests can patch it at the module boundary: `patch("src.agent.tools.MOCK_USERS", ...)`.
- The tool imports `MOCK_USERS` at the top of `tools.py`:
  `from src.agent.fixtures import MOCK_USERS` — this is fine because the dict
  is a pure literal with no side effects.
- No `ctx.deps` fields are used in this tool — `RunContext[Settings]` is kept
  as the first parameter for consistency with the other tools and the agent's
  `deps_type=Settings`.
