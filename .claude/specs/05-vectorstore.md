# Spec 05 — Vectorstore

## Feature
Ingest embeddings from `data/stripe_embeddings.jsonl` into Qdrant with
joined chunk metadata as payload, and expose a `retrieve(query, top_k)`
function that returns the most semantically similar chunks for a
natural-language query.

## Why
Embeddings on disk are useless for retrieval. Qdrant provides fast
approximate nearest-neighbour search over vectors. We ingest once,
then every retrieval is a single sub-second API call.

## Input contracts
- `data/stripe_chunks.jsonl` — provides metadata (url, title, text)
- `data/stripe_embeddings.jsonl` — provides vectors

The two files are joined on `chunk_id`.

## Qdrant collection design
- Name: `stripe_docs`
- Vector size: 512
- Distance: `Cosine`
- Point structure:
  - id: chunk_id (string)
  - vector: 512-dim float array
  - payload:
    {
      "doc_url": str,
      "doc_title": str,
      "chunk_index": int,
      "text": str,          # full chunk text, needed downstream for generation
      "token_count": int
    }

## Scope (in)
- `src/rag/vectorstore.py` with:
  - `QdrantStore` class wrapping the Qdrant client
    - `__init__(url: str, collection: str, api_key: str = "")` — connects to Qdrant Cloud
      when `api_key` is set; falls back to unauthenticated for local dev. Does NOT auto-create.
    - `create_collection(recreate: bool = False)` — creates with correct config;
      if `recreate=True`, drops and recreates (destructive; requires --recreate flag)
    - `upsert_batch(points: list[PointStruct]) -> None`
    - `search(query_vector: list[float], top_k: int = 5) -> list[dict]`
      — returns list of `{chunk_id, score, doc_url, doc_title, text, chunk_index}`
    - `count() -> int` — returns number of points in collection
  - `ingest(chunks_path: Path, embeddings_path: Path, batch_size: int = 256) -> dict`
    — joins the two files by chunk_id, upserts in batches, returns stats
  - Standalone `retrieve(query: str, top_k: int = 5) -> list[dict]` function
    that:
    1. Embeds `query` via VoyageEmbedder with `input_type="query"` (not "document")
    2. Calls `QdrantStore.search`
    3. Returns the list of hits
- CLI entries:
  - `python -m src.rag.vectorstore ingest` — runs ingestion end-to-end
  - `python -m src.rag.vectorstore ingest --recreate` — drops collection first
  - `python -m src.rag.vectorstore search "how do I refund a payment"` — CLI for testing retrieval
- Tests in `tests/test_vectorstore.py`:
  - Join logic: given fake chunks + fake embeddings, produces correct joined points
  - Missing embedding for a chunk_id: skip with warning
  - Extra embedding with no matching chunk: skip with warning
  - `QdrantStore.search` with mocked Qdrant client returns expected shape
  - `retrieve()` end-to-end with mocked Voyage + mocked Qdrant

## Scope (out)
- Filtering by payload fields (add later if needed)
- Reranking (later phase)
- Hybrid search (BM25 + vector) — later, if quality is bad
- Streaming ingestion progress bar — nice-to-have, skip

## Query embedding vs document embedding — IMPORTANT
Voyage's API takes an `input_type` parameter. Documents are embedded with
`input_type="document"` (Feature 4). Queries must be embedded with
`input_type="query"`. Using the same type for both silently hurts
retrieval quality. This must be reflected in code.

## Failure modes
- Qdrant unreachable: raise with `QDRANT_URL` in message
- `QDRANT_API_KEY` missing when connecting to a cloud URL (non-localhost): raise with clear message
- Collection already exists on ingest without --recreate: refuse to run,
  print instructions
- Chunk missing from either file during join: skip with warning
- Empty query string: raise ValueError
- top_k <= 0: raise ValueError

## Dependencies
- Existing: `qdrant-client`, `voyageai`
- No new deps

## Acceptance criteria
1. Qdrant Cloud cluster is reachable: `curl -H "api-key: $QDRANT_API_KEY" $QDRANT_URL` returns version JSON
2. `uv run python -m src.rag.vectorstore ingest` completes without error
3. `QdrantStore.count()` returns 4319
4. `uv run python -m src.rag.vectorstore search "how do I issue a refund?"`
   returns 5 hits, each with a Stripe URL and a text snippet
5. The top hit for "how do I issue a refund" mentions refunds
   (eyeball check — semantic match must actually work)
6. The top hit for "webhook signing" mentions webhooks
7. The top hit for "create a subscription" mentions subscriptions
8. Re-running ingest without --recreate errors out with a clear message
9. `uv run pytest tests/test_vectorstore.py` passes
10. `uv run ruff check src/rag/vectorstore.py` passes
11. No network calls in tests (mock both Qdrant and Voyage)

## Notes
- The eyeball tests (#5-7) are the actual proof retrieval works. If a
  query about refunds returns chunks about webhooks, something is
  broken — most likely the query is being embedded as a document.
- Payload will contain the full chunk text. Qdrant handles this fine at
  this scale, and it saves a second lookup at generation time.
- Cost: query embeddings are billed. At ~50 tokens per query and $0.02/M
  tokens, you'd need 1M queries to spend $1. Not a concern.