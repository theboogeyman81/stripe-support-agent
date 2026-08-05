# Spec 15 — Tool: Search Docs

## Feature
Register a `search_docs` Pydantic AI tool on the agent that wraps the existing
`retrieve()` function from `src/rag/vectorstore.py`. When the agent decides it
needs Stripe documentation to answer a question, it calls this tool with a query
string and receives back a formatted block of relevant chunks. No other tools,
no endpoint changes — just the tool wired into the agent from feature 14.

## Why
Feature 14 created a bare agent that answers from its training data alone.
Attaching `search_docs` gives the agent grounding: it can now decide when to
look up the Stripe docs corpus instead of relying on its own knowledge. This is
the core RAG-in-agent pattern that replaces the fixed pipeline from Phase 1/2.

## Input contract
- `src/rag/vectorstore.py` — `retrieve(query: str, top_k: int = 5) -> list[dict]`
  (already exists; each dict has `chunk_id`, `score`, `doc_url`, `doc_title`,
  `text`, `chunk_index`)
- `src/agent/agent.py` — `create_agent()` and `run_agent()` from feature 14
- `src/config.py` — `Settings` (needs `voyage_api_key`, `qdrant_url`,
  `qdrant_api_key`)

## Output contract

### `src/agent/tools.py` (new)
One public function:

```python
def search_docs(ctx: RunContext[Settings], query: str) -> str:
    """Search Stripe docs for chunks relevant to query; return formatted text."""
```

- Calls `retrieve(query, top_k=5)` internally.
- Returns a single formatted string the model can read, one chunk per section:
  ```
  [1] <doc_title>
  URL: <doc_url>
  <text>

  [2] ...
  ```
- If `retrieve()` returns an empty list, returns the string
  `"No relevant documentation found."`.
- Raises `ValueError` if `query` is empty or whitespace (mirrors existing
  guards in the codebase).

### Changes to `src/agent/agent.py`
- Add `deps_type=Settings` to the `Agent(...)` constructor.
- Pass `tools=[search_docs]` to the `Agent(...)` constructor.
- Change `agent.run_sync(question)` → `agent.run_sync(question, deps=settings)`
  in `run_agent()`.

### No changes to
- `src/rag/vectorstore.py` — consumed as-is.
- Any API routes — the `/ask` endpoint stays on the Phase 1/2 pipeline.

## Scope (in)
- `src/agent/tools.py` — new file, `search_docs` function
- `src/agent/agent.py` — modify `create_agent` and `run_agent` to wire deps
- `tests/test_tools.py` — new test file
- `tests/test_agent.py` — update existing tests broken by the `deps` change

## Scope (out)
- No changes to `retrieve()` or any RAG module
- No `top_k` parameter exposed to the agent (fixed at 5)
- No tool result caching (Phase 6)
- No other tools (features 16–18)
- No `/chat` endpoint (feature 21)

## Dependencies
- New: none
- Existing: `src/rag/vectorstore.retrieve`, `pydantic_ai.RunContext`, `src/config.Settings`

## Acceptance criteria
1. `uv run python -c "from src.agent.tools import search_docs; print('OK')"` exits 0.
2. `uv run pytest tests/test_tools.py -v` passes (all external calls mocked).
3. `uv run pytest tests/test_agent.py -v` still passes after the deps changes.
4. `uv run ruff check src/agent/tools.py src/agent/agent.py` exits 0.
5. Live smoke test (costs < $0.001 — confirm before running):
   ```
   uv run python -c "
   from src.config import Settings
   from src.agent.agent import run_agent
   r = run_agent('What is a PaymentIntent?', Settings())
   print(r['answer'][:120])
   "
   ```
   Returns a non-empty answer that references Stripe docs content.

## Failure modes to handle
- `query` is empty or whitespace: raise `ValueError("query must not be empty")`.
- `retrieve()` returns empty list: return `"No relevant documentation found."` —
  do not raise; let the agent handle the lack of results.
- `retrieve()` raises (Qdrant or Voyage unreachable): let the exception propagate
  to Pydantic AI, which surfaces it as a tool error to the model.

## Notes
- Pydantic AI tools that need runtime dependencies (Settings, API keys) use
  `RunContext[DepType]` as the first parameter. The dep is passed at call time
  via `agent.run_sync(question, deps=settings)`. This keeps the tool pure and
  testable — mock the `ctx.deps` in tests.
- `retrieve()` already initialises its own Voyage and Qdrant clients from
  `Settings()` internally. The `ctx.deps` in `search_docs` gives access to the
  same `Settings` object passed to `run_agent`, so no double-initialisation.
- The formatted string return (not a list) is intentional: Gemini receives the
  tool result as text it appends to the conversation. A clean numbered block is
  easier for the model to cite than raw JSON.
