# Spec 26 — Trace Retrieval

## Feature
Add a Langfuse span inside `retrieve()` in `src/rag/vectorstore.py` that logs
the query, requested `top_k`, and the result set (count, titles, scores) for
every vector search. If the Langfuse client is absent, `retrieve()` runs exactly
as before — no crash, no behaviour change.

## Why
Features 24 and 25 trace the LLM call and tool calls. The retrieval step
(embed query → search Qdrant → return chunks) is the remaining unobserved leg.
A retrieval span lets you see in Langfuse what query the agent searched for, how
many chunks came back, and what their relevance scores were — essential for
debugging RAG quality without re-running the full pipeline.

## Input contract
- `src/rag/vectorstore.py` — `retrieve()` function (lines 170–185); it already
  calls `settings = Settings()` internally
- `src/observability/langfuse_client.py` — `get_langfuse_client(settings)`
  from feature 23

## Output contract

### `src/rag/vectorstore.py` (modify)

Add one import at the top (after existing imports):

```python
from src.observability.langfuse_client import get_langfuse_client
```

Modify `retrieve()` to wrap `store.search()` in a Langfuse span using the
`settings` object already created inside the function:

```python
def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Embed query and return top_k semantically similar chunks from Qdrant."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if top_k <= 0:
        raise ValueError("top_k must be > 0")

    settings = Settings()
    embedder = VoyageEmbedder(client=voyageai.Client(api_key=settings.voyage_api_key))
    query_vector = embedder.embed_query(query)
    store = QdrantStore(
        url=settings.qdrant_url,
        collection=COLLECTION,
        api_key=settings.qdrant_api_key,
    )
    client = get_langfuse_client(settings)
    span = (
        client.start_observation(
            name="retrieve",
            as_type="span",
            input={"query": query, "top_k": top_k},
        )
        if client else None
    )
    try:
        results = store.search(query_vector, top_k=top_k)
        if span:
            span.update(output={
                "result_count": len(results),
                "scores": [r["score"] for r in results],
                "titles": [r["doc_title"] for r in results],
            })
        return results
    finally:
        if span:
            span.end()
```

Only `store.search()` and the return are inside the `try/finally` — embedding
and store construction happen before the span opens.

### `tests/test_vectorstore.py` (modify)

Two changes:

**1. Update the existing `test_retrieve_uses_query_input_type` mock Settings**
to include `langfuse_public_key=""` and `langfuse_secret_key=""` so
`get_langfuse_client` returns `None` and the test is unaffected:

```python
monkeypatch.setattr(
    "src.rag.vectorstore.Settings",
    lambda: MagicMock(
        voyage_api_key="vk",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="",
        langfuse_public_key="",
        langfuse_secret_key="",
    ),
)
```

**2. Add two new tests:**

| Test | Setup | Expected |
|------|-------|---------|
| `test_retrieve_creates_langfuse_span` | monkeypatch Settings + Voyage + Qdrant clients; mock `get_langfuse_client` → mock client | `client.start_observation` called with `name="retrieve"`, `as_type="span"`, `input={"query": ..., "top_k": ...}`; `span.end()` called once |
| `test_retrieve_skips_span_when_client_absent` | monkeypatch as above; mock `get_langfuse_client` → `None` | no exception; returns list |

Both new tests use `monkeypatch.setattr("src.rag.vectorstore.get_langfuse_client", ...)`.

## Scope (in)
- `src/rag/vectorstore.py` — add import + span inside `retrieve()`
- `tests/test_vectorstore.py` — update one existing test + add 2 new tests

## Scope (out)
- Tracing `ingest()` — not needed for support agent observability
- Nesting the retrieval span under the feature-25 `search_docs` tool span —
  feature 27 (session grouping) will link observations by trace/session ID
- Logging the actual chunk text in the span output — titles + scores are
  sufficient; full text would bloat the trace payload
- Any changes to routes, agent, tools, config, or schemas

## Dependencies
- New: none
- Existing: `src/observability/langfuse_client.get_langfuse_client`

## Acceptance criteria
1. `uv run pytest tests/test_vectorstore.py -v` passes (all existing + 2 new).
2. `uv run ruff check src/rag/vectorstore.py` exits 0.
3. `uv run pytest -q` — full suite (151+) passes with no regressions.
4. Live smoke test — send `"What is a PaymentIntent?"` via `/chat`, open
   Langfuse UI, confirm a span named `retrieve` appears with `query` and
   `scores` in its output payload.

## Failure modes to handle
- `get_langfuse_client` returns `None` (keys missing): `span` is `None`, all
  `if span:` guards are skipped — `retrieve()` is unchanged.
- `store.search()` raises: `finally: span.end()` fires regardless, ending
  the span before the exception propagates.

## Notes
- `retrieve()` already calls `Settings()` internally, so calling
  `get_langfuse_client(settings)` adds zero extra I/O or config reads.
- The span wraps only `store.search()`, not the embed step — the Voyage embed
  call has its own latency and will get its own span in a future feature if
  needed. For now, the retrieval span captures end-to-end wall time from search
  start to results returned.
