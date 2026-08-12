# Spec 32 — Retrieval Eval

## Feature
A script (`scripts/run_retrieval_eval.py`) that measures retrieval quality
against the golden dataset using two standard IR metrics:

- **Recall@k** — proportion of questions where at least one `ideal_url` appears
  in the top-k retrieved chunks.
- **MRR (Mean Reciprocal Rank)** — average of 1/rank of the first relevant
  chunk across all questions; 0 if no relevant chunk appears in top-k.

A helper module `src/eval/retrieval_metrics.py` holds the pure metric
functions (no I/O, fully testable). The script loops over the golden dataset,
calls `retrieve()` per question, applies the metrics, and writes
`data/retrieval_results.json`.

## Why
Ragas and the LLM judge evaluate generation quality. Neither tells you whether
the right document pages are being surfaced at all. Recall@k and MRR give a
retrieval-specific baseline that feature 33 (pytest-eval-suite) can enforce as
a threshold, and that future changes to chunking/embedding parameters can be
measured against.

## Input contract
- `data/golden_dataset.jsonl` — one record per line:
  ```json
  {
    "id": "q001",
    "question": "...",
    "reference_answer": "...",
    "ideal_urls": ["https://docs.stripe.com/..."]
  }
  ```
- `retrieve(query, top_k)` from `src/rag/vectorstore.py` — returns:
  ```json
  [{"chunk_id": "...", "score": 0.91, "doc_url": "...", "doc_title": "...", "text": "...", "chunk_index": 0}]
  ```

## Output contract
`data/retrieval_results.json`:
```json
{
  "recall_at_k": 0.875,
  "mrr": 0.712,
  "k": 5,
  "items_evaluated": 40,
  "items_skipped": 0,
  "timestamp": "2026-08-12T10:00:00+00:00"
}
```

Field rules:
- `recall_at_k`: float 0.0–1.0; fraction of questions with ≥1 ideal URL in
  top-k results.
- `mrr`: float 0.0–1.0; mean reciprocal rank across all questions (0 for
  questions with no relevant hit).
- `k`: the value of `--top-k` used (default 5).
- `timestamp`: ISO-8601, UTC.

## Scope (in)
- `src/eval/retrieval_metrics.py` — new file:
  - `recall_at_k(retrieved_urls: list[str], ideal_urls: list[str]) -> float`
  - `reciprocal_rank(retrieved_urls: list[str], ideal_urls: list[str]) -> float`
- `scripts/run_retrieval_eval.py` — new runner:
  - Loads golden dataset, calls `retrieve()` per question, computes metrics,
    prints summary, writes `data/retrieval_results.json`.
  - No paid LLM calls; no cost estimate or confirmation prompt required.
- `tests/test_retrieval_metrics.py` — new test file.

## Scope (out)
- No changes to `retrieve()`, `vectorstore.py`, or any existing file.
- No Langfuse integration.
- No Precision@k or nDCG (MRR and Recall@k are sufficient for this phase).
- No async evaluation.

## Dependencies
- New: none. Uses existing `src/rag/vectorstore.py` and `src/eval/` package.
- Existing: `src/rag/vectorstore.retrieve`, `src/config.Settings`,
  `data/golden_dataset.jsonl`.

## Acceptance criteria
1. `uv run python -m scripts.run_retrieval_eval --help` exits 0 and lists
   `--path`, `--top-k` flags.
2. `uv run pytest tests/test_retrieval_metrics.py -v` — all tests pass with
   zero network calls.
3. `uv run ruff check src/eval/retrieval_metrics.py scripts/run_retrieval_eval.py`
   — no errors.
4. (Live APIs) `uv run python -m scripts.run_retrieval_eval` exits 0 and writes
   `data/retrieval_results.json` containing `recall_at_k` and `mrr` keys:
   ```powershell
   python -c "import json; d=json.load(open('data/retrieval_results.json')); assert 'recall_at_k' in d and 'mrr' in d; print('OK')"
   ```

## Failure modes to handle
- `retrieve()` raises (e.g. Qdrant unreachable): print warning, skip item,
  increment `items_skipped`.
- A question's `ideal_urls` list contains a URL that does not exactly match any
  `doc_url` in retrieved chunks: count as a miss (score 0 for that question).
  URL matching is exact string equality — no normalisation.
- No items successfully evaluated: print error and `sys.exit(1)`.

## Notes
- `retrieve()` returns `doc_url` per chunk. A chunk is considered relevant if
  its `doc_url` matches any entry in the question's `ideal_urls`. Because
  multiple chunks can come from the same URL, deduplication is not needed —
  only the rank of the *first* matching chunk matters for MRR.
- `recall_at_k` and `reciprocal_rank` are pure functions (no I/O, no
  side effects). This makes them trivial to unit-test with inline fixtures.
- No cost confirmation is needed: this script only calls `retrieve()` (Voyage
  AI embeddings), which is on the free tier and costs effectively $0 for 40
  queries.
- URL matching: `ideal_urls` values in the golden dataset are canonical Stripe
  doc URLs (e.g. `https://docs.stripe.com/payments/payment-intents`). The
  `doc_url` stored in Qdrant comes from the same source, so exact matching
  is reliable.
