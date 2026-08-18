# Spec 25 — Trace Tool Calls

## Feature
Add a Langfuse span to each of the four agent tools (`search_docs`,
`calculate`, `create_ticket`, `lookup_user`) so that every tool invocation
appears as an observable span in Langfuse. Each span captures the tool name,
its input arguments, and its return value. If the Langfuse client is absent
(keys not configured), the tool runs exactly as before — no crash, no change in
behaviour.

## Why
Feature 24 emits one aggregate generation span per agent turn. That span shows
total tokens and cost but does not reveal which tools were called or what they
returned. This feature adds the fine-grained view: each tool call becomes its
own Langfuse span, letting you see the full reasoning chain in the UI. Features
26 (retrieval tracing) and 27 (session grouping) build on these spans.

## Input contract
- `src/agent/tools.py` — the four existing tool functions
- `src/observability/langfuse_client.py` — `get_langfuse_client(settings)`
  from feature 23

## Output contract

### `src/agent/tools.py` (modify)

Each tool follows this pattern (using `search_docs` as the example):

```python
from src.observability.langfuse_client import get_langfuse_client

def search_docs(ctx: RunContext[Settings], query: str) -> str:
    """Search Stripe docs for chunks relevant to query; return formatted text."""
    if not query.strip():
        raise ValueError("query must not be empty")
    client = get_langfuse_client(ctx.deps)
    span = (
        client.start_observation(name="search_docs", as_type="span", input={"query": query})
        if client else None
    )
    try:
        chunks = retrieve(query, top_k=5)
        if not chunks:
            result = "No relevant documentation found."
        else:
            sections = []
            for i, chunk in enumerate(chunks, 1):
                sections.append(
                    f"[{i}] {chunk['doc_title']}\n"
                    f"URL: {chunk['doc_url']}\n"
                    f"{chunk['text']}"
                )
            result = "\n\n".join(sections)
        if span:
            span.update(output=result)
        return result
    finally:
        if span:
            span.end()
```

Span arguments per tool:

| Tool | `name` | `input` dict |
|------|--------|-------------|
| `search_docs` | `"search_docs"` | `{"query": query}` |
| `calculate` | `"calculate"` | `{"expression": expression}` |
| `create_ticket` | `"create_ticket"` | `{"category": category, "summary": summary}` |
| `lookup_user` | `"lookup_user"` | `{"email": email}` |

All spans use `as_type="span"`. The `output` is set to the return string via
`span.update(output=result)` before `span.end()`. Errors propagate normally;
the `finally` block ensures the span is always ended.

### `tests/test_tools.py` (modify)

Add one tracing test per tool (span created when client present) and one shared
test verifying the absent-client path:

| Test | Tool | Setup | Expected |
|------|------|-------|---------|
| `test_search_docs_creates_span` | `search_docs` | mock `get_langfuse_client` → mock client; mock `retrieve` → `[]` | `client.start_observation` called with `name="search_docs"`, `as_type="span"` |
| `test_calculate_creates_span` | `calculate` | mock `get_langfuse_client` → mock client | `client.start_observation` called with `name="calculate"`, `as_type="span"` |
| `test_create_ticket_creates_span` | `create_ticket` | mock `get_langfuse_client` → mock client; mock `insert_ticket` | `client.start_observation` called with `name="create_ticket"`, `as_type="span"` |
| `test_lookup_user_creates_span` | `lookup_user` | mock `get_langfuse_client` → mock client | `client.start_observation` called with `name="lookup_user"`, `as_type="span"` |
| `test_search_docs_skips_span_when_client_absent` | `search_docs` | mock `get_langfuse_client` → `None`; mock `retrieve` → `[]` | no exception; returns valid string |

Mock target: `src.agent.tools.get_langfuse_client` (patched at the import
boundary in `tools.py`, same pattern used throughout this test suite).

## Scope (in)
- `src/agent/tools.py` — add Langfuse span to each of the 4 tool functions
- `tests/test_tools.py` — 5 new tracing tests

## Scope (out)
- Nesting tool spans under the feature-24 generation span — feature 27
  (session grouping) will link them by trace/session ID
- Separate retrieval span inside `search_docs` — feature 26
- Error-level span status on exceptions — future hardening
- Any changes to routes, agent, config, or schemas

## Dependencies
- New: none
- Existing: `src/observability/langfuse_client.get_langfuse_client`

## Acceptance criteria
1. `uv run pytest tests/test_tools.py -v` passes (all existing + 5 new tests).
2. `uv run ruff check src/agent/tools.py` exits 0.
3. Live smoke test — send a question via `/chat` that triggers a tool call
   (e.g. `"What is a PaymentIntent?"` triggers `search_docs`), open Langfuse
   UI, confirm a span named `search_docs` appears.

## Failure modes to handle
- `get_langfuse_client` returns `None`: `span` is `None`, `if span:` guards
  skip all Langfuse calls — tool runs normally.
- Tool raises an exception: `finally: span.end()` fires regardless, ending the
  span cleanly before the exception propagates to the agent.

## Notes
- Each tool call creates its own `Langfuse` client instance via
  `get_langfuse_client(ctx.deps)`. The `Langfuse()` constructor is lightweight
  (lazy connection) so multiple instances per request are fine.
- Spans created here are not automatically nested under the feature-24 trace.
  They appear as sibling observations in Langfuse. Session grouping (feature 27)
  will link them.
- `ctx.deps` is the `Settings` instance injected by Pydantic AI — same object
  used to initialise the Langfuse client in feature 24.
