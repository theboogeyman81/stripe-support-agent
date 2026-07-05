# Spec 04 — Embedder

## Feature
Embed every chunk in `data/stripe_chunks.jsonl` using Voyage AI and
write the resulting vectors to `data/stripe_embeddings.jsonl`.

## Why
Vector search requires every chunk to have a vector representation.
Voyage's `voyage-3-lite` is the chosen embedding model: small, cheap,
high quality, generous free tier. Embedding is a one-shot offline
process — we do it once, save the vectors, and reuse them for
retrieval, re-indexing, and experimentation without re-paying.

## Input contract
File: `data/stripe_chunks.jsonl`
Each line:
{
  "chunk_id": str,
  "doc_url": str,
  "doc_title": str,
  "chunk_index": int,
  "text": str,
  "token_count": int
}

## Output contract
File: `data/stripe_embeddings.jsonl`
Each line:
{
  "chunk_id": str,        # same id as input — used to join with chunks later
  "model": "voyage-3-lite",
  "dim": 512,
  "embedding": [float, ...]   # length == dim
}

We intentionally do NOT duplicate chunk text or metadata here.
Embeddings file is paired with the chunks file by chunk_id.

## Model + parameters
- Model: `voyage-3-lite`
- Dimension: 512 (model default)
- Input type: `"document"` (Voyage distinguishes document vs query embeddings;
  we use "document" for indexing the corpus)

## Scope (in)
- `src/rag/embedder.py` with:
  - `VoyageEmbedder` class wrapping the Voyage client
    - `embed_batch(texts: list[str]) -> list[list[float]]`
    - One retry with exponential backoff on transient errors (rate limit, 5xx)
  - `embed_corpus(input_path: Path, output_path: Path, batch_size: int = 128) -> dict`
    - Reads chunks JSONL
    - Batches into groups of `batch_size`
    - Calls Voyage per batch
    - Appends results to output JSONL as it goes (crash-safe — never lose progress)
    - Skips chunks whose chunk_id is already in the output file (resume support)
    - Returns stats dict
- Add `VOYAGE_API_KEY` reference in `src/config.py` (already declared, just used)
- CLI entry: `python -m src.rag.embedder` runs end-to-end on the full corpus
- Stats printed:
  - Total chunks in input
  - Already embedded (skipped)
  - Newly embedded
  - Total tokens sent
  - Estimated cost
  - Elapsed time
  - Avg ms per batch
- Tests in `tests/test_embedder.py`:
  - `embed_batch` with a **mocked** Voyage client returns correct shape
  - Resume logic: with a partial output file, second run only embeds missing ids
  - Output JSONL has correct schema (use mocked vectors)
  - **No network calls in tests**

## Scope (out)
- Qdrant upsert (next feature)
- Query embeddings (different input_type — handled in retriever feature)
- Reranking
- Embedding model comparison or A/B
- Async / parallel batching (sequential is fine; Voyage is fast)

## Cost guardrails — REQUIRED
Before any embedding call is made, the CLI must:
1. Compute total input tokens across all unembedded chunks (sum of token_count)
2. Compute estimated cost: `total_tokens * 0.00000002`  (voyage-3-lite: $0.02 / 1M tokens)
3. Print: "About to embed N chunks (~M tokens). Estimated cost: $X. Proceed? [y/N]"
4. Wait for stdin confirmation. Default is "No".
5. A `--yes` flag bypasses the prompt for automation. Never set as default.

This is a hard requirement. We are not surprising ourselves with a bill.

## Failure modes
- Voyage API key missing: raise with clear message before any HTTP call
- Rate limit (429): one retry after exponential backoff (1s, 2s); then fail loudly
- Batch failure mid-corpus: write progress, raise, instruct user to re-run (resume will pick up)
- Empty batch / empty text: skip with warning
- Chunk text exceeds model's max input tokens (32k for voyage-3-lite): warn, truncate to 32k tokens

## Dependencies
- New: `voyageai` (Voyage's official Python client)
- Existing: stdlib, tiktoken (only if needed for token-truncation safety net)

## Acceptance criteria
1. `uv run python -m src.rag.embedder --yes` runs to completion against the real corpus
2. `data/stripe_embeddings.jsonl` exists with exactly 4319 lines (1 per chunk)
3. Every record has: `chunk_id`, `model == "voyage-3-lite"`, `dim == 512`, `embedding` of length 512
4. Every embedding has all numeric values, no NaN, no nulls
5. chunk_ids in embeddings file exactly match chunk_ids in chunks file (no extras, no missing)
6. Re-running `uv run python -m src.rag.embedder --yes` does ~zero new work (resume works)
7. `uv run pytest tests/test_embedder.py` passes
8. `uv run ruff check src/rag/embedder.py` passes
9. No network calls in tests
10. Actual cost printed at the end matches (within $0.01) the estimated cost

## Notes
- Cost ballpark: 4319 chunks × ~461 median tokens ≈ 2M tokens × $0.02/M = ~$0.04
  Voyage free tier covers 200M tokens. We're at 1% of free tier.
- Resume support is non-negotiable. Embedding 4000+ chunks takes minutes,
  not seconds. A crash 80% in must not re-bill us for the first 80%.
- Output is JSONL not Parquet/NPY for human-debuggability in Phase 1.
  May revisit if file size becomes a problem.