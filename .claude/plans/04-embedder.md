# Plan: 04 — Embedder

## Context

The RAG pipeline needs every chunk in `data/stripe_chunks.jsonl` embedded as a 512-dim vector
so Qdrant can do vector search later. Voyage AI's `voyage-3-lite` model is chosen: cheap
($0.02/1M tokens), high quality, and the free tier covers our ~2M-token corpus many times over.
Embedding is a one-shot offline step — run once, persist, never re-pay.

The input file (`stripe_chunks.jsonl`) has 4319 lines. Each line carries a `token_count` field,
which the chunker already computed. We exploit this for cost estimation without a second tokenizer pass.

---

## 1. Voyage Client Initialization

`src/config.py` already declares `voyage_api_key: str` via `pydantic-settings`. Reading it requires
only `from src.config import Settings; settings = Settings()`. Pydantic raises a clear `ValidationError`
if the key is missing from the environment, satisfying the "fail before any HTTP call" requirement.

`VoyageEmbedder.__init__` receives the key and calls `voyageai.Client(api_key=api_key)` once.
The resulting client object is stored as `self._client`. No module-level singletons.

---

## 2. Batching Strategy — Streaming, Never Full-Load

```
stripe_chunks.jsonl  ──► iterator (one line at a time)
    │
    ▼ skip if chunk_id in embedded_ids set
    │
    ▼ accumulate in buffer (list[dict], len ≤ batch_size=128)
    │
    ▼ when buffer full (or end of file):
        texts = [r["text"] for r in buffer]
        vectors = embedder.embed_batch(texts)
        for chunk, vec in zip(buffer, vectors):
            fout.write(json.dumps({
                "chunk_id": chunk["chunk_id"],
                "model": "voyage-3-lite",
                "dim": 512,
                "embedding": vec,
            }) + "\n")
        fout.flush()       # ← crash-safe; progress survives a kill
        buffer.clear()
```

Pattern mirrors `chunk_corpus` in `src/rag/chunker.py:126-166`:
- Both open input/output files with a `with` block
- Both iterate line-by-line, skipping blank/malformed lines
- Both write and flush incrementally

Memory at any point: one batch of 128 chunks (≈ 64 KB of text). Not 4319 chunks.

---

## 3. Resume Logic

```python
def _load_embedded_ids(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    ids = set()
    with output_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    ids.add(json.loads(line)["chunk_id"])
                except (json.JSONDecodeError, KeyError):
                    pass  # corrupt tail line from a crash; ignore
    return ids
```

Called at the top of `embed_corpus` before the main loop. The set is O(1) lookup.
Output file is opened in **append mode** (`"a"`), so existing records are preserved.

On re-run: `_load_embedded_ids` returns all 4319 ids → the loop skips every chunk → zero API calls.

---

## 4. Cost Estimation and Prompt

Located in `embed_corpus` (before any API call), controlled by `yes: bool = False` parameter.

```python
# After building embedded_ids, one scan of input to count unembedded tokens:
total_chunks = 0
to_embed_tokens = 0
to_embed_count = 0
# read input once to gather stats; store (chunk_id, token_count) tuples
# Then:
estimated_cost = to_embed_tokens * 0.00000002  # $0.02 / 1M

if not yes:
    print(
        f"About to embed {to_embed_count} chunks "
        f"(~{to_embed_tokens:,} tokens). "
        f"Estimated cost: ${estimated_cost:.4f}. "
        f"Proceed? [y/N] ",
        end="",
        flush=True,
    )
    answer = input()
    if answer.strip().lower() != "y":
        print("Aborted.")
        raise SystemExit(0)
```

The single-scan strategy: iterate input_path once to build `(chunk_id, text, token_count)` tuples
for unembedded chunks, stored as a list. This list is then fed into the batching loop — avoids
reading the file twice. Memory: list of lightweight dicts (no embeddings yet).

`--yes` is parsed in `__main__` via `argparse` and passed into `embed_corpus(... yes=args.yes)`.

---

## 5. Retry Logic

```python
MAX_RETRIES = 2          # 3 total attempts: original + 2 retries
_BACKOFFS = [1.0, 2.0]  # seconds to sleep before retry 1 and retry 2

def embed_batch(self, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    last_exc = None
    for attempt, backoff in enumerate([(0,)] + list(zip(_BACKOFFS))):
        # sleep 0 before first attempt, 1s before second, 2s before third
        ...
```

Cleaner implementation:

```python
_RETRY_SLEEPS = [1.0, 2.0]  # sleep before retry i

def embed_batch(self, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    last_exc: Exception | None = None
    for attempt in range(len(_RETRY_SLEEPS) + 1):
        if attempt > 0:
            time.sleep(_RETRY_SLEEPS[attempt - 1])
        try:
            result = self._client.embed(texts, model="voyage-3-lite", input_type="document")
            return result.embeddings
        except Exception as exc:
            last_exc = exc
            log.warning("Voyage API error (attempt %d): %s", attempt + 1, exc)
    raise RuntimeError(f"Voyage API failed after {len(_RETRY_SLEEPS)+1} attempts") from last_exc
```

Catching broad `Exception` is intentional: the `voyageai` SDK wraps all HTTP errors, and we want
any transient failure (429, 5xx, connection reset) to retry. Non-transient errors (auth, bad model
name) will just fail on every retry and surface clearly in the `RuntimeError`.

Warn-and-truncate for oversized chunks (> 32k tokens): check `len(text.split())` as a cheap proxy
before the API call; if suspicious, use tiktoken to confirm and truncate.

---

## 6. Test Design

File: `tests/test_embedder.py`

All tests use `unittest.mock.patch` — no network calls.

### Mock setup shared across tests

```python
FAKE_VEC = [0.1] * 512

def make_mock_client(n_texts=None):
    """Returns a mock voyageai.Client whose .embed() returns FAKE_VEC per text."""
    mock = MagicMock()
    def _embed(texts, **kwargs):
        result = MagicMock()
        result.embeddings = [FAKE_VEC[:] for _ in texts]
        return result
    mock.embed.side_effect = _embed
    return mock
```

### Tests

| # | Name | Setup | Assert |
|---|------|--------|--------|
| 1 | `test_embed_batch_shape` | patch `voyageai.Client` → `make_mock_client()`; call `embed_batch(["a","b","c"])` | returns list of 3 vectors each of length 512 |
| 2 | `test_embed_batch_empty` | no mock needed; call `embed_batch([])` | returns `[]`; `voyageai.Client.embed` never called |
| 3 | `test_embed_batch_retry_succeeds` | mock raises `Exception("rate limit")` on call 1, succeeds on call 2 | `embed.call_count == 2`; returns valid vectors |
| 4 | `test_embed_batch_fails_after_retries` | mock always raises | `RuntimeError` raised; `embed.call_count == 3` |
| 5 | `test_resume_skips_existing_ids` | write output JSONL with 1 of 3 chunk_ids; input has 3; `embed_corpus(yes=True)` | mock called for exactly 2 chunks (1 batch of 2) |
| 6 | `test_full_resume_no_work` | output has all 3 chunk_ids; `embed_corpus(yes=True)` | mock `embed` never called; stats `newly_embedded==0` |
| 7 | `test_output_schema` | 3-chunk input; mocked Voyage; `embed_corpus(yes=True)` | output JSONL has 3 lines; each has `chunk_id`, `model=="voyage-3-lite"`, `dim==512`, `embedding` of length 512; all floats |
| 8 | `test_cost_prompt_yes_flag` | `yes=True`; patch `builtins.input` → `MagicMock()` | `input` never called; embed proceeds |
| 9 | `test_cost_prompt_aborts_on_no` | `yes=False`; patch `builtins.input` → returns `"n"` | `SystemExit(0)` raised; `embed` never called |

Tests use `tmp_path` (pytest fixture) for input/output files — no disk pollution.

---

## 7. Files to Create / Modify

| File | Action | Notes |
|------|--------|-------|
| `src/rag/embedder.py` | **Implement** | Replace 1-line stub |
| `tests/test_embedder.py` | **Create** | 9 tests |
| `src/config.py` | No change | `voyage_api_key` already declared |
| `pyproject.toml` | No change | `voyageai` already a dependency |
| `.env.example` | No change | `VOYAGE_API_KEY=` already present |

---

## 8. `embedder.py` Module Structure

```
VoyageEmbedder
  __init__(api_key: str)
  embed_batch(texts: list[str]) -> list[list[float]]   # with retry

_load_embedded_ids(output_path: Path) -> set[str]

embed_corpus(
    input_path: Path,
    output_path: Path,
    batch_size: int = 128,
    yes: bool = False,
) -> dict   # {total, skipped, newly_embedded, tokens_sent, cost, elapsed_s, avg_ms_per_batch}

if __name__ == "__main__":
    argparse (--yes), logging setup, Settings(), VoyageEmbedder(key), embed_corpus(), print stats
```

---

## 9. Verification — PowerShell Commands

```powershell
# AC1: end-to-end run
uv run python -m src.rag.embedder --yes

# AC2: exactly 4319 lines
(Get-Content data\stripe_embeddings.jsonl | Measure-Object -Line).Lines

# AC3–AC5: schema + id parity
uv run python -c @"
import json
from pathlib import Path
chunks = {json.loads(l)['chunk_id'] for l in Path('data/stripe_chunks.jsonl').open(encoding='utf-8')}
embs = [json.loads(l) for l in Path('data/stripe_embeddings.jsonl').open(encoding='utf-8')]
assert len(embs) == 4319, f'Expected 4319, got {len(embs)}'
for e in embs:
    assert e['model'] == 'voyage-3-lite'
    assert e['dim'] == 512
    assert len(e['embedding']) == 512
    assert all(isinstance(v, float) for v in e['embedding']), 'Non-float in embedding'
assert {e['chunk_id'] for e in embs} == chunks, 'chunk_id mismatch'
print('All schema checks passed')
"@

# AC6: re-run does zero new work
uv run python -m src.rag.embedder --yes

# AC7: tests
uv run pytest tests/test_embedder.py -v

# AC8: lint
uv run ruff check src/rag/embedder.py
```

---

## Key Invariants

- Output file opened in **append** mode (`"a"`) so a crash never loses previously written embeddings.
- `fout.flush()` called after every batch write.
- Cost prompt reads `token_count` from the input JSONL (pre-computed by chunker) — no second tokenizer pass.
- `yes=True` in `embed_corpus` means no `input()` call anywhere in the call path.
- Voyage model hardcoded to `"voyage-3-lite"` and `input_type="document"` inside `embed_batch`; callers don't pass model names.
