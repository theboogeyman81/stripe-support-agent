# Plan 05 — Vectorstore

## Context

Feature 05 closes the ingest loop: embeddings are on disk, now they need to live in Qdrant so the retriever can do ANN search. We're using **Qdrant Cloud** (free tier) instead of the Docker-based setup in the README, because the dev machine runs Windows 11 Home without Docker support. The cluster URL and API key live in `.env`; `src/config.py` already has `qdrant_url` and `qdrant_api_key` fields.

The two deliverables are:
1. `QdrantStore` — a thin wrapper around `QdrantClient` for upsert and search
2. `retrieve(query, top_k)` — the function `src/ask.py` will call in Phase 1

---

## qdrant-client v1.18.0 API facts (confirmed from installed package)

| Need | Call |
|---|---|
| Connect | `QdrantClient(url=url, api_key=api_key or None)` |
| Collection exists | `client.collection_exists(collection_name) -> bool` |
| Create collection | `client.create_collection(collection_name, vectors_config=VectorParams(size=512, distance=Distance.COSINE))` |
| Delete collection | `client.delete_collection(collection_name)` |
| Upsert | `client.upsert(collection_name, points=[PointStruct(...)])` |
| Search | `client.query_points(collection_name, query=[float,...], limit=top_k, with_payload=True)` → `QueryResponse` |
| Result fields | `response.points` → list of `ScoredPoint(id, score, payload)` |

**Imports:**
```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
```

**Point IDs**: `PointStruct.id` accepts `int | str | UUID`. Qdrant server requires integer or UUID format — `chunk_id` strings like `"stripe-42331f8a-0"` are NOT valid UUIDs. Use `str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))` to get a deterministic, collision-free UUID per chunk. Store original `chunk_id` in payload so search hits can return it.

---

## 1. Files to create / modify

| File | Change |
|---|---|
| `src/rag/vectorstore.py` | Create from stub — the whole feature |
| `src/rag/embedder.py` | Add `embed_query(text) -> list[float]` to `VoyageEmbedder` |
| `tests/test_vectorstore.py` | Create — all tests |

`src/config.py`, `pyproject.toml`, `.env.example` already updated. No new deps.

---

## 2. Change to `src/rag/embedder.py`

Add one method to `VoyageEmbedder`. `embed_batch` hardcodes `input_type="document"` — query embedding requires `input_type="query"`, which Voyage treats differently for retrieval quality.

```python
def embed_query(self, text: str) -> list[float]:
    """Embed a single query string with input_type='query'."""
    result = self._client.embed([text], model=MODEL, input_type="query")
    return result.embeddings[0]
```

No retry here — query embedding is interactive (user is waiting) and a single token. If it fails, let it raise immediately. No new tests needed (covered by the retrieve end-to-end mock test in test_vectorstore.py).

---

## 3. `src/rag/vectorstore.py` — full structure

### Module-level constants
```python
CHUNKS_PATH = Path("data/stripe_chunks.jsonl")
EMBEDDINGS_PATH = Path("data/stripe_embeddings.jsonl")
COLLECTION = "stripe_docs"
VECTOR_SIZE = 512
```

### `QdrantStore` class

```python
class QdrantStore:
    def __init__(self, url: str, collection: str, api_key: str = "") -> None:
```

**Connection logic:**
- If `url` does not contain `localhost` or `127.0.0.1` and `api_key` is empty → raise `ValueError` with clear message naming `QDRANT_API_KEY`
- Pass `api_key=api_key or None` to `QdrantClient` (passing empty string would be wrong — cloud requires `None` when absent)

```python
    def create_collection(self, recreate: bool = False) -> None:
```
- `exists = self._client.collection_exists(self._collection)`
- If `exists and not recreate` → raise `RuntimeError` with instructions to pass `--recreate`
- If `exists and recreate` → call `self._client.delete_collection(self._collection)`
- Then `self._client.create_collection(self._collection, vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE))`

```python
    def upsert_batch(self, points: list[PointStruct]) -> None:
```
- `self._client.upsert(collection_name=self._collection, points=points)`

```python
    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict]:
```
- `response = self._client.query_points(self._collection, query=query_vector, limit=top_k, with_payload=True)`
- Return list of dicts: `{chunk_id, score, doc_url, doc_title, text, chunk_index}` pulled from `pt.payload` for each `pt in response.points`

```python
    def count(self) -> int:
```
- `return self._client.count(self._collection).count`

### `ingest()` function

```python
def ingest(
    chunks_path: Path,
    embeddings_path: Path,
    store: QdrantStore,
    batch_size: int = 256,
) -> dict:
```

**Join algorithm** — two-pass, memory for embeddings only (~8.5 MB):

```
Pass 1: stream embeddings_path → build dict[chunk_id → embedding]
        O(N) time, O(N × 512 × 8 bytes) ≈ 17 MB RAM

Pass 2: stream chunks_path line by line
        for each chunk:
            look up chunk["chunk_id"] in embeddings dict
            if missing → log.warning, n_skipped_chunks++, continue
            build PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"])),
                vector=embeddings[chunk_id],
                payload={chunk_id, doc_url, doc_title, chunk_index, text, token_count}
            )
            append to current batch
            if len(batch) == batch_size:
                store.upsert_batch(batch); batch = []

        if batch: store.upsert_batch(batch)

After pass 1: check for extra embeddings (embeddings not consumed by pass 2)
        extra_ids = set(embeddings.keys()) - set of chunk_ids seen in pass 2
        for each → log.warning
```

**Return dict:**
```python
{
    "total_chunks": int,
    "total_embeddings": int,
    "upserted": int,
    "skipped_no_embedding": int,
    "extra_embeddings": int,
}
```

### `retrieve()` standalone function

```python
def retrieve(query: str, top_k: int = 5) -> list[dict]:
```

Flow:
1. Guard: `if not query.strip(): raise ValueError("query must not be empty")`
2. Guard: `if top_k <= 0: raise ValueError("top_k must be > 0")`
3. `settings = Settings()` — reads `.env`
4. `embedder = VoyageEmbedder(client=voyageai.Client(api_key=settings.voyage_api_key))`
5. `query_vector = embedder.embed_query(query)` ← `input_type="query"` happens inside here
6. `store = QdrantStore(url=settings.qdrant_url, collection=COLLECTION, api_key=settings.qdrant_api_key)`
7. `return store.search(query_vector, top_k=top_k)`

---

## 4. CLI — argparse subcommands

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qdrant vectorstore CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Upsert chunks+embeddings into Qdrant")
    p_ingest.add_argument("--recreate", action="store_true",
                          help="Drop and recreate collection (destructive)")

    p_search = sub.add_parser("search", help="Test retrieval from Qdrant")
    p_search.add_argument("query", help="Natural language query")
    p_search.add_argument("--top-k", type=int, default=5)

    args = parser.parse_args()

    if args.cmd == "ingest":
        # build store, call create_collection(recreate=args.recreate), call ingest()
        # print stats
    elif args.cmd == "search":
        # call retrieve(args.query, args.top_k)
        # print hits
```

---

## 5. Tests — `tests/test_vectorstore.py`

All tests use `MagicMock`. No network calls. Pattern matches `test_embedder.py`.

### Helpers
```python
def _write_chunks(path, records):  # writes JSONL with chunk schema
def _write_embeddings(path, records):  # writes JSONL with embedding schema
def _fake_chunk(chunk_id, **overrides): -> dict
def _fake_embedding(chunk_id, dim=512): -> dict
```

### Test list

| Test | What it verifies | Mock setup |
|---|---|---|
| `test_join_correct` | 3 chunks + 3 embeddings → 3 PointStructs upserted with correct payload | Mock `QdrantStore.upsert_batch`, capture calls |
| `test_join_missing_embedding` | chunk with no matching embedding → skipped, warning logged | `caplog`, 2 chunks 1 embedding |
| `test_join_extra_embedding` | embedding with no matching chunk → reported in stats | 1 chunk 2 embeddings |
| `test_join_stats_keys` | returned dict has all required keys | 2 chunks 2 embeddings |
| `test_search_returns_correct_shape` | `QdrantStore.search` returns `[{chunk_id, score, doc_url, ...}]` | Mock `QdrantClient`, return fake `ScoredPoint`-like objects with `.score` and `.payload` |
| `test_search_uses_limit` | `query_points` called with correct `limit` | Capture call args |
| `test_retrieve_uses_query_input_type` | `embed_query` is called (not `embed_batch`), `input_type="query"` used | Mock `VoyageEmbedder`, mock `QdrantStore` |
| `test_retrieve_empty_query_raises` | `ValueError` on empty string | No mocks needed |
| `test_retrieve_zero_top_k_raises` | `ValueError` on `top_k=0` | No mocks needed |
| `test_collection_exists_without_recreate_raises` | `ingest` aborts if collection already exists | Mock `collection_exists -> True` |
| `test_cloud_url_without_api_key_raises` | non-localhost URL + empty api_key → `ValueError` | No mocks needed |

**Mock pattern for `search` test** — build a fake `ScoredPoint`-like object:
```python
hit = MagicMock()
hit.score = 0.95
hit.payload = {"chunk_id": "x-0", "doc_url": "https://...", "doc_title": "T",
               "text": "some text", "chunk_index": 0}
mock_client.query_points.return_value = MagicMock(points=[hit])
```

---

## 6. Acceptance criterion PowerShell commands

```powershell
# 1. Cluster reachable
$url = (Get-Content .env | Select-String "QDRANT_URL").ToString().Split("=",2)[1]
$key = (Get-Content .env | Select-String "QDRANT_API_KEY").ToString().Split("=",2)[1]
curl -H "api-key: $key" $url

# 2. Ingest
uv run python -m src.rag.vectorstore ingest

# 3. Count
uv run python -c "
from src.config import Settings; from src.rag.vectorstore import QdrantStore, COLLECTION
s = Settings(); store = QdrantStore(s.qdrant_url, COLLECTION, s.qdrant_api_key)
print(store.count())
"

# 4-7. Search eyeball tests
uv run python -m src.rag.vectorstore search "how do I issue a refund?"
uv run python -m src.rag.vectorstore search "webhook signing"
uv run python -m src.rag.vectorstore search "create a subscription"

# 8. Re-run ingest without --recreate (should error)
uv run python -m src.rag.vectorstore ingest

# 9. Tests
uv run pytest tests/test_vectorstore.py -v

# 10. Lint
uv run ruff check src/rag/vectorstore.py src/rag/embedder.py
```

---

## Key risks / decisions

- **UUID conversion**: chunk_ids are not valid UUIDs. `uuid.uuid5(uuid.NAMESPACE_URL, chunk_id)` → deterministic, collision-free, server-accepted. `chunk_id` string always stored in payload and returned in hits.
- **`query_points` not `search`**: v1.18.0's current API is `query_points(..., limit=top_k)`. The older `search()` method still exists but `query_points` is the recommended path.
- **`api_key=None` vs `""`**: `QdrantClient` treats empty string as "no key". Pass `api_key=api_key if api_key else None`.
- **`embed_query` addition to embedder.py**: Small additive change; existing tests unaffected since they don't call this method.
