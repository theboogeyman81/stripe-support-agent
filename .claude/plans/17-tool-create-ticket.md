# Plan — Feature 17: Tool Create Ticket

## Context

The agent can search docs and do arithmetic, but has no way to persist a support
ticket when a user describes a billing problem. This feature adds a Postgres-backed
`create_ticket` tool and the DB layer beneath it. Raw `psycopg` (sync), no ORM,
no migration runner — the table creates itself on first use.

---

## Files to create or modify

| File | Action | Purpose |
|------|---------|---------|
| `pyproject.toml` | **Modify** | Add `psycopg[binary]` dependency |
| `src/config.py` | **Modify** | Add `postgres_url: str = ""` field to `Settings` |
| `src/db/__init__.py` | **Create** | Empty — makes `src.db` a package |
| `src/db/tickets.py` | **Create** | `ensure_tickets_table` + `insert_ticket` |
| `src/agent/tools.py` | **Modify** | Add `create_ticket` tool |
| `src/agent/agent.py` | **Modify** | Add `create_ticket` to `tools=[]` |
| `tests/test_db_tickets.py` | **Create** | Tests for the DB layer (psycopg mocked) |
| `tests/test_tools.py` | **Modify** | Add tests for `create_ticket` |
| `.env.example` | **Modify** | Document `POSTGRES_URL` |

---

## Algorithm walkthrough

### `src/db/tickets.py`

**`ensure_tickets_table(postgres_url: str) -> None`**

Opens a connection, runs `CREATE TABLE IF NOT EXISTS`, commits, closes.

```python
import psycopg

def ensure_tickets_table(postgres_url: str) -> None:
    """Create the tickets table if it does not exist."""
    with psycopg.connect(postgres_url) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id         SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                category   TEXT NOT NULL,
                summary    TEXT NOT NULL
            )
        """)
        conn.commit()
```

**`insert_ticket(postgres_url: str, category: str, summary: str) -> int`**

Calls `ensure_tickets_table` first (self-bootstrapping), then inserts one row
and retrieves the generated id in the same round-trip via `RETURNING id`.

```python
def insert_ticket(postgres_url: str, category: str, summary: str) -> int:
    """Insert one ticket row and return the new ticket id."""
    ensure_tickets_table(postgres_url)
    with psycopg.connect(postgres_url) as conn:
        row = conn.execute(
            "INSERT INTO tickets (category, summary) VALUES (%s, %s) RETURNING id",
            (category, summary),
        ).fetchone()
        conn.commit()
    return row[0]
```

`psycopg3` uses `%s` placeholders (not `?`) and `fetchone()` returns a tuple.
`row[0]` is the `id`. No second SELECT needed.

### `src/agent/tools.py` — add `create_ticket`

```python
from src.db.tickets import insert_ticket

def create_ticket(ctx: RunContext[Settings], category: str, summary: str) -> str:
    """Create a support ticket in Postgres and return a confirmation string."""
    if not ctx.deps.postgres_url:
        raise ValueError("postgres_url is not configured")
    ticket_id = insert_ticket(ctx.deps.postgres_url, category, summary)
    return f"Ticket #{ticket_id} created (category: {category})."
```

### `src/agent/agent.py` — one-line change

```python
# before
from src.agent.tools import calculate, search_docs
tools=[search_docs, calculate]

# after
from src.agent.tools import calculate, create_ticket, search_docs
tools=[search_docs, calculate, create_ticket]
```

### `src/config.py` — one-line addition

```python
postgres_url: str = ""  # empty default keeps existing tests unaffected
```

---

## Test design

### `tests/test_db_tickets.py` (new)

All psycopg calls are mocked via `unittest.mock.patch`. We never open a real
connection in tests.

**Mock setup pattern:**

```python
from unittest.mock import MagicMock, patch

def _make_conn_mock(returning_id: int = 1) -> MagicMock:
    row = (returning_id,)
    cursor_mock = MagicMock()
    cursor_mock.fetchone.return_value = row
    conn_mock = MagicMock()
    conn_mock.execute.return_value = cursor_mock
    conn_mock.__enter__ = lambda s: s   # support `with psycopg.connect(...) as conn`
    conn_mock.__exit__ = MagicMock(return_value=False)
    return conn_mock
```

| Test | What it verifies |
|------|-----------------|
| `test_ensure_tickets_table_executes_create` | `conn.execute` called with SQL containing `CREATE TABLE IF NOT EXISTS tickets` |
| `test_ensure_tickets_table_commits` | `conn.commit()` called |
| `test_insert_ticket_calls_ensure_first` | `ensure_tickets_table` is called before the INSERT (patch both) |
| `test_insert_ticket_returns_id` | return value equals `row[0]` from the mocked cursor |
| `test_insert_ticket_uses_parameterised_query` | `conn.execute` called with `%s` placeholders, not string interpolation |

### `tests/test_tools.py` additions

The tool is thin — it delegates to `insert_ticket`. We mock `insert_ticket`
via `patch("src.agent.tools.insert_ticket", ...)`.

```python
def _ctx_with_postgres() -> MagicMock:
    ctx = MagicMock(spec=RunContext)
    ctx.deps.postgres_url = "postgresql://fake/db"
    return ctx

def _ctx_no_postgres() -> MagicMock:
    ctx = MagicMock(spec=RunContext)
    ctx.deps.postgres_url = ""
    return ctx
```

| Test | Setup | Expected |
|------|-------|---------|
| `test_create_ticket_returns_confirmation` | `insert_ticket` returns `1` | `"Ticket #1 created (category: billing)."` |
| `test_create_ticket_empty_url_raises` | `postgres_url = ""` | `ValueError("postgres_url is not configured")` |
| `test_create_ticket_passes_args_to_insert` | check `insert_ticket` called with correct args | `insert_ticket("postgresql://fake/db", "billing", "I was double-charged")` |

---

## Ambiguities — resolved

| Ambiguity | Resolution |
|-----------|-----------|
| Should `ensure_tickets_table` open its own connection or share with `insert_ticket`? | Separate connections — simpler, keeps functions independently testable, and connection overhead is negligible for a dev project (spec says no pooling). |
| `psycopg3` vs `psycopg2` placeholder style? | `psycopg3` uses `%s` — same as `psycopg2`, confirmed in docs. |
| `conn.commit()` needed? | Yes — `psycopg3` does NOT auto-commit by default; DDL and DML both need explicit commit. |
| Import order in `tools.py`? | `from src.db.tickets import insert_ticket` goes in the stdlib/third-party/local block. Ruff will sort it. |

---

## Verification commands (PowerShell)

```powershell
# AC1 — DB module imports cleanly
uv run python -c "from src.db.tickets import ensure_tickets_table, insert_ticket; print('OK')"

# AC2 — tool imports cleanly
uv run python -c "from src.agent.tools import create_ticket; print('OK')"

# AC3 — all mocked tests pass
uv run pytest tests/test_db_tickets.py tests/test_tools.py -v

# AC4 — ruff clean
uv run ruff check src/db/tickets.py src/agent/tools.py src/agent/agent.py

# AC5 — live integration test (requires POSTGRES_URL in .env)
uv run python -c "
from src.config import Settings
from src.db.tickets import insert_ticket
tid = insert_ticket(Settings().postgres_url, 'billing', 'Test ticket')
print(f'Created ticket #{tid}')
"
```
