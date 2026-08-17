# Spec 17 — Tool: Create Ticket

## Feature
Add a `create_ticket` Pydantic AI tool that inserts a support ticket row into a
Postgres database and returns the new ticket ID to the agent. When a user
describes a billing problem, account issue, or anything that can't be answered
from the docs, the agent calls this tool instead of (or after) calling
`search_docs`. This is the first feature that touches a relational database.

## Why
The phase-3 exit checklist requires ticket rows persisting in Postgres and the
agent choosing `create_ticket` for account/billing complaints. This feature
provides the DB layer and the tool. Features 18–21 build on top of it.

## Input contract
- `src/config.py` — `Settings` must gain a new field `postgres_url: str`
- A Postgres database reachable at that URL, with no pre-existing schema
  required — the tool creates the table on first use via `CREATE TABLE IF NOT
  EXISTS`
- No migration runner or ORM — raw SQL via `psycopg`

## Output contract

### `src/config.py` (modify)
Add one field to `Settings`:
```python
postgres_url: str = ""
```
Empty default so existing tests that construct `Settings(...)` without a
`postgres_url` do not break.

### `src/db/__init__.py` (new)
Empty — makes `src.db` a package.

### `src/db/tickets.py` (new)
Two public functions:

```python
def ensure_tickets_table(postgres_url: str) -> None:
    """Create the tickets table if it does not exist."""

def insert_ticket(postgres_url: str, category: str, summary: str) -> int:
    """Insert one ticket row and return the new ticket id."""
```

Table schema (created by `ensure_tickets_table`):
```sql
CREATE TABLE IF NOT EXISTS tickets (
    id        SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category  TEXT NOT NULL,
    summary   TEXT NOT NULL
)
```

`insert_ticket` calls `ensure_tickets_table` first so the tool is
self-bootstrapping — no separate migration step needed for a dev environment.
Returns the `id` of the inserted row.

### `src/agent/tools.py` (modify)
Add one new public tool function:

```python
def create_ticket(ctx: RunContext[Settings], category: str, summary: str) -> str:
    """Create a support ticket in Postgres and return a confirmation string."""
```

- Calls `insert_ticket(ctx.deps.postgres_url, category, summary)`.
- Returns `f"Ticket #{ticket_id} created (category: {category})."`.
- Raises `ValueError("postgres_url is not configured")` if
  `ctx.deps.postgres_url` is empty — gives the agent a clear error message
  rather than a cryptic connection failure.

### Changes to `src/agent/agent.py`
- Add `create_ticket` to `tools=[...]` in `create_agent()`. No other changes.

### `.env.example` (modify)
Add `POSTGRES_URL=postgresql://user:password@host:5432/dbname` as a commented
example line.

## Scope (in)
- `src/db/__init__.py` — new, empty
- `src/db/tickets.py` — new, two public functions
- `src/agent/tools.py` — add `create_ticket` tool
- `src/agent/agent.py` — add `create_ticket` to `tools=[]`
- `src/config.py` — add `postgres_url` field
- `tests/test_db_tickets.py` — new test file for the DB layer
- `tests/test_tools.py` — add tests for `create_ticket`
- `.env.example` — document the new env var

## Scope (out)
- No ticket listing or retrieval endpoint (Phase 4+)
- No ticket status updates or resolution workflow
- No ORM or migration runner — raw SQL only
- No async — `psycopg` used in sync mode
- No connection pooling — a fresh connection per call is fine for dev
- No changes to any API routes

## Dependencies
- New: `psycopg[binary]` — **must be approved before adding to pyproject.toml**.
  This is the psycopg3 driver. The `[binary]` extra ships pre-compiled wheels
  so no C build tools are needed on Windows.
- Existing: `pydantic_ai.RunContext`, `src/config.Settings`

## Acceptance criteria
1. `uv run python -c "from src.db.tickets import ensure_tickets_table, insert_ticket; print('OK')"` exits 0.
2. `uv run python -c "from src.agent.tools import create_ticket; print('OK')"` exits 0.
3. `uv run pytest tests/test_db_tickets.py tests/test_tools.py -v` passes (all DB calls mocked).
4. `uv run ruff check src/db/tickets.py src/agent/tools.py src/agent/agent.py` exits 0.
5. Live integration test against a real Postgres instance (requires `POSTGRES_URL` set in `.env`):
   ```
   uv run python -c "
   from src.config import Settings
   from src.db.tickets import insert_ticket
   tid = insert_ticket(Settings().postgres_url, 'billing', 'Test ticket')
   print(f'Created ticket #{tid}')
   "
   ```
   Prints `Created ticket #1` (or incremented id). No cost.

## Failure modes to handle
- `postgres_url` empty in `create_ticket` tool: raise `ValueError("postgres_url is not configured")`.
- Postgres unreachable in `insert_ticket`: let `psycopg.OperationalError` propagate — Pydantic AI surfaces it as a tool error, the agent can relay a graceful message.
- Table already exists: `CREATE TABLE IF NOT EXISTS` is idempotent — not an error.

## Notes
- The user's machine has no Docker support (Windows 11 Home). A cloud Postgres
  is required. Free options: Supabase, Neon, Railway. Any will work — just
  set `POSTGRES_URL` in `.env`.
- `psycopg[binary]` (psycopg3) is preferred over `psycopg2-binary`: cleaner
  API, no OS build tools needed, Windows wheels are available on PyPI.
- `insert_ticket` uses a `RETURNING id` clause: `INSERT INTO tickets (...) VALUES (...) RETURNING id`
  and fetches the single returned row to get the new id — avoids a second
  round-trip or lastrowid workarounds.
- The `postgres_url` default of `""` in Settings means all existing tests that
  pass keyword args to `Settings(gemini_api_key=..., voyage_api_key=..., ...)` 
  continue to work without modification.
