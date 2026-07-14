# Learnings: 04 — Embedder

---

## Why this feature exists

**What:** The embedder reads every chunk in `data/stripe_chunks.jsonl`, calls Voyage AI's `voyage-3-lite` model, and writes `data/stripe_embeddings.jsonl` — one `{"chunk_id", "model", "dim", "embedding"}` record per chunk.
**Why:** Vector search needs a vector per chunk. Embedding is a one-shot, offline, *paid* process — done once, saved, reused forever for retrieval and re-indexing without re-paying. That "costs real money" property is what shapes almost every other design decision below.
**How:** `uv run python -m src.rag.embedder --yes` reads `data/stripe_chunks.jsonl` → writes `data/stripe_embeddings.jsonl`. Embeddings are stored separately from chunk text/metadata and joined later by `chunk_id`, so re-embedding never requires re-writing the chunks file.

---

## Don't guess a third-party SDK's surface — introspect it

**What:** Before writing any code against `voyageai`, the actual installed package was introspected at runtime (`inspect.signature(voyageai.Client.embed)`, `dir(voyageai.error)`) rather than relying on the spec text or training-data memory of the library.
**Why:** This caught a real discrepancy: the spec's retry logic assumed a `Timeout` error class existed on `voyageai.error`, but it doesn't — the actual exports are `RateLimitError`, `ServerError`, `ServiceUnavailableError`, `APIConnectionError`, `TryAgain`, `AuthenticationError`, `InvalidRequestError`, `MalformedRequestError`, all subclassing `VoyageError` with no shared "transient" base class.
**How:** `_RETRYABLE` in `src/rag/embedder.py` is an explicit tuple of only the confirmed-real, confirmed-transient classes — no speculative catches. If this had been written from memory instead of introspection, `_RETRYABLE` would have referenced a class that raises `AttributeError` at import time.

---

## Lazy client construction for testability

**What:** `VoyageEmbedder.__init__` accepts an optional `client: voyageai.Client | None`. When `None`, it builds a real client from `Settings().voyage_api_key`; when a client is passed in, that's used as-is.
**Why:** `Settings()` requires `VOYAGE_API_KEY` to be set (via `.env` or environment) or it raises a `pydantic` validation error. If the client were built as a module-level singleton (the pattern chunker uses for its tiktoken encoder — see [[03-chunker]]), simply importing `src.rag.embedder` would fail in any environment missing the key, including CI and fresh checkouts before `.env` exists. Constructing it lazily inside `__init__`, and only when no client is injected, means `import src.rag.embedder` always succeeds.
**How:** Every test constructs `VoyageEmbedder(client=MagicMock())`, so `voyageai.Client(...)` and `Settings()` are never touched during `pytest` — confirmed by running the full suite with `VOYAGE_API_KEY`/`GEMINI_API_KEY` unset (`env -u VOYAGE_API_KEY -u GEMINI_API_KEY uv run pytest`) and it still passes. "No network calls in tests" isn't just discipline here, it's structurally impossible to violate by accident.

---

## Cost guardrail: collect everything before spending anything

**What:** `embed_corpus` does a full pass over the input JSONL — applying resume-skip, empty-text-skip, and oversized-text-truncation — and only *then* computes `total_tokens` / `estimated_cost` and shows the y/N prompt. The Voyage client is never touched until after confirmation.
**Why:** The spec calls this a hard requirement: never surprise the user with a bill. That means the total must be known and shown *before* the first paid call, not accumulated as a running total during the calls themselves — the whole point is the user gets to say no first.
**How:**
```python
if not pending:
    print("Nothing to embed — all chunks already have embeddings.")
    return {...}

total_tokens = sum(t for _, _, t in pending)
estimated_cost = total_tokens * COST_PER_TOKEN
print(f"About to embed {len(pending)} chunks (~{total_tokens} tokens). "
      f"Estimated cost: ${estimated_cost:.4f}. Proceed? [y/N] ", end="")
if not auto_confirm and not _prompt_confirm():
    return {..., "aborted": True}
```
The empty-`pending` case returns immediately with no prompt at all — this is also what makes "re-running does ~zero new work" a clean, promptless no-op rather than an annoying "proceed? [y/N]" for zero chunks.

---

## Resume is a pre-pass, not a filter during the batch loop

**What:** `_load_done_ids` reads the *existing* output file once, up front, into a `set[str]` of `chunk_id`s. The main input-reading pass then skips any chunk already in that set inline, in the same loop that builds `pending`.
**Why:** This keeps resume detection and cost estimation as the same single pass over the input file — the token total shown in the cost prompt is *already* resume-aware (only unembedded chunks count), so the estimate never overstates cost for a partially-completed run.
**How:** A truncated last line in the output file (e.g. from a crash mid-`json.dumps`) is caught by `json.JSONDecodeError`, logged as a warning, and simply not added to `done`— so that one chunk gets harmlessly re-embedded rather than the whole resume mechanism breaking on a corrupt line.

---

## Batch-atomic writes: flush after every batch, never truncate

**What:** The output file is opened once in `"a"` (append) mode for the whole run. After each batch's vectors come back from Voyage, each one is written as its own JSON line and the file is `flush()`-ed before moving to the next batch.
**Why:** If the process dies mid-corpus (network blip, rate limit exhausted, `Ctrl-C`), every batch that completed before the crash is already durably on disk. Re-running the CLI picks up exactly where it left off via `_load_done_ids` — no double-billing for chunks already embedded, no data loss for chunks that were.
**How:** A batch is all-or-nothing: `embed_batch` either returns a full list of vectors for the whole batch or raises (after the retry is exhausted). There's no code path that writes a partial batch, so a resumed run always restarts cleanly at a batch boundary, never mid-batch.

---

## Resolving a spec ambiguity: "one retry" vs "(1s, 2s)"

**What:** The spec's Scope section said "one retry with exponential backoff"; its Failure modes section said "one retry after exponential backoff (1s, 2s)" — ambiguous between 2 total attempts (1 retry, 1s wait) and 3 total attempts (2 retries, 1s then 2s waits).
**Why it mattered:** Silently picking one reading would bake an unverified assumption into billing-relevant retry behavior. Retrying an extra time isn't free — it's an extra paid API call.
**How resolved:** Asked the user directly rather than guessing; confirmed as **2 attempts total (1 retry)**. Implemented as a fixed `range(2)` loop with a single 1-second sleep between attempts:
```python
for attempt in range(2):
    try:
        result = self.client.embed(texts, model=self.model, input_type="document")
        ...
        return result.embeddings
    except _RETRYABLE as exc:
        if attempt == 1:
            raise
        time.sleep(1)
```
**Lesson:** When a spec contradicts itself on something that affects cost or irreversible behavior, treat it as a real ambiguity to resolve explicitly, not a rounding error to interpret charitably.

---

## Truncation and empty-text skips happen before cost estimation, not after

**What:** Oversized text (> `MAX_INPUT_TOKENS` = 32,000, matching voyage-3-lite's limit) is truncated via the same `tiktoken` `cl100k_base` encoding chunker already uses (`_ENC.decode(token_ids[:MAX_INPUT_TOKENS])`), and empty/whitespace-only text is skipped — both during the same single pass that builds `pending`, before any token totals are computed.
**Why:** If truncation happened *after* the cost estimate, the estimate would overstate real spend for oversized chunks (Voyage bills on what's actually sent, not what's in the file). Doing it inline in the same pass keeps the printed estimate and the eventual actual cost close — the spec's acceptance criterion requires them to match within $0.01.
