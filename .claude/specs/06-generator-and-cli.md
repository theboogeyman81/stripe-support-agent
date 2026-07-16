# Spec 06 — Generator and CLI

## Feature
Implement `src/rag/generator.py` (Gemini 2.5 Flash answer generation with
citation prompting and token-cost accounting), `src/ingest.py` (full pipeline
orchestrator: load → chunk → embed → upsert), and `src/ask.py` (end-to-end
CLI: retrieve → generate → print answer with cited sources and cost). This
completes Phase 1.

## Why
Features 01–05 built each RAG layer in isolation. This feature wires them
together into a working product: one command to ingest Stripe docs, one command
to ask a question and get a grounded, cited answer. After this, Phase 1's exit
checklist is fully runnable.

## Input contract
`src/rag/generator.py`:
- `question: str` — the user's natural-language question
- `chunks: list[dict]` — retrieved hits from `vectorstore.retrieve()`, each
  with keys: `text`, `doc_url`, `doc_title`, `score`, `chunk_index`, `chunk_id`
- `top_k: int = 5` — how many chunks are passed in (used only for prompt header)

`src/ingest.py` (CLI, no library input):
- Reads `data/stripe_docs.jsonl`, `data/stripe_chunks.jsonl`,
  `data/stripe_embeddings.jsonl` from the project root
- All pipeline steps use existing functions from features 02–05

`src/ask.py` (CLI):
- Positional arg: `question` — the user's question string

## Output contract
`generator.generate()` returns a `dict`:
```json
{
  "answer":        "<Gemini's response text>",
  "input_tokens":  1234,
  "output_tokens": 256,
  "cost_usd":      0.000123
}
```
- `answer`: stripped response text; never empty
- `input_tokens` / `output_tokens`: from `response.usage_metadata`
- `cost_usd`: computed as `(input_tokens / 1_000_000) * INPUT_PRICE + (output_tokens / 1_000_000) * OUTPUT_PRICE`

`src/ingest.py` prints to stdout:
```
Loaded    : <N> documents
Chunked   : <N> chunks
Embedded  : <N> vectors  (skipped <N>)
Upserted  : <N> points
Collection: stripe_docs
```

`src/ask.py` prints to stdout:
```
Answer:
<Gemini answer text>

Sources:
[1] <doc_title> — <doc_url>
[2] ...

Tokens : <input_tokens> in / <output_tokens> out
Cost   : $<cost_usd:.6f>
```
Only sources actually cited in the answer (by `[1]`, `[2]` markers) need not
be filtered — print all retrieved sources; the prompt instructs Gemini to
cite them.

## Scope (in)
- `src/rag/generator.py`:
  - `GEMINI_MODEL = "gemini-2.5-flash"` constant
  - `INPUT_PRICE_PER_M = 0.30` and `OUTPUT_PRICE_PER_M = 2.50` (USD per 1M
    tokens — Gemini 2.5 Flash standard tier; verify against current pricing
    before commit)
  - `build_prompt(question: str, chunks: list[dict]) -> str` — formats the
    RAG prompt (see Notes for template)
  - `generate(question: str, chunks: list[dict]) -> dict` — initialises the
    Gemini client from `Settings`, calls `build_prompt`, sends to Gemini,
    reads `usage_metadata`, computes cost, returns the result dict
- `src/ingest.py`:
  - `__main__` block with `argparse`; accepts `--yes` flag to skip cost
    confirmation
  - Calls `loader.load()` → `chunker.chunk_documents()` → `embedder.embed_*`
    → `vectorstore.ingest()` in sequence, printing stats at each stage
  - Cost discipline: before embedding step, print estimated Voyage cost and
    prompt `Proceed? [y/N]` (default No); skip if `--yes`
  - If `data/stripe_embeddings.jsonl` already exists and is non-empty, skip
    the embed step and print `Embeddings already exist — skipping embed step.`
    (resume-safety, consistent with Feature 04's design)
- `src/ask.py`:
  - `__main__` block; positional `question` arg, optional `--top-k` (default 5)
    and `--yes` flag
  - Cost discipline: before generation, print estimated Gemini cost (based on
    prompt token count from a dry-run or rough estimate) and prompt
    `Proceed? [y/N]`; skip if `--yes`
  - Calls `vectorstore.retrieve(question, top_k)` → `generator.generate(question, chunks)` → prints formatted output
- `tests/test_generator.py`:
  - `test_build_prompt_includes_question` — question appears in returned string
  - `test_build_prompt_includes_chunk_text` — each chunk's text appears in returned string
  - `test_build_prompt_includes_chunk_urls` — each chunk's `doc_url` appears in returned string
  - `test_generate_returns_expected_shape` — mock Gemini client; returned dict has
    all four keys with correct types
  - `test_generate_cost_calculation` — given known token counts in mock, verify
    `cost_usd` arithmetic
  - `test_generate_raises_on_empty_question` — `ValueError` for blank question
  - `test_generate_raises_on_empty_chunks` — `ValueError` for empty chunk list

## Scope (out)
- Streaming responses (later phase)
- Conversation memory / multi-turn (Phase 2+)
- Re-ranking retrieved chunks (later phase)
- Retry logic on Gemini API errors (later phase)
- `--dry-run` flag that estimates cost without calling Gemini (future)
- Filtering or deduplicating sources by URL

## Dependencies
- New: none (`google-genai` already in `pyproject.toml`)
- Existing: `src/rag/loader.py`, `src/rag/chunker.py`, `src/rag/embedder.py`,
  `src/rag/vectorstore.py`, `src/config.py`

## Prompt template (generator)
```
You are a Stripe support assistant. Answer the user's question using ONLY the
provided documentation excerpts below. Do not use outside knowledge.

For each fact you state, cite the source by its number, e.g. [1] or [2].
If the excerpts do not contain enough information to answer, say so — do not
guess.

--- Documentation excerpts ---

[1] {doc_title}
URL: {doc_url}
{text}

[2] ...

--- Question ---
{question}

--- Answer ---
```

## Acceptance criteria
1. `uv run python -m src.ingest --yes` completes without error; prints stats
   showing chunks loaded, embeddings skipped (already exist), and N points
   upserted.
2. `uv run python -m src.ask "How do I create a refund?" --yes` prints a
   non-empty answer that mentions refunds, at least one Stripe URL, and a cost
   line like `Cost   : $0.000xxx`.
3. `uv run python -m src.ask "What is webhook signing?" --yes` — answer
   mentions webhooks/signatures and cites at least one source URL.
4. `uv run python -m src.ask "How do subscriptions work?" --yes` — answer
   mentions subscriptions/billing and cites at least one source URL.
5. Running `uv run python -m src.ask "..."` without `--yes` shows a cost
   estimate and `Proceed? [y/N]` prompt; entering `n` exits without calling
   Gemini.
6. `uv run pytest tests/test_generator.py` passes (7 tests, no network calls).
7. `uv run pytest` passes (all tests across all modules).
8. `uv run ruff check src/rag/generator.py src/ingest.py src/ask.py` is clean.

## Failure modes to handle
- Empty `question` string passed to `generate()`: raise `ValueError("question must not be empty")`
- Empty `chunks` list passed to `generate()`: raise `ValueError("chunks must not be empty")`
- Gemini API key missing or invalid: let the `google-genai` exception propagate
  (no wrapping needed — the error message is clear)
- `data/stripe_chunks.jsonl` missing when running `src/ingest.py`: print a
  clear error pointing to Feature 02/03 and exit with code 1
- `data/stripe_embeddings.jsonl` missing when running `src/ingest.py`: print
  a clear error pointing to Feature 04 and exit with code 1

## Notes
- `google-genai` client init: `from google import genai; client = genai.Client(api_key=...)`
  Generation: `client.models.generate_content(model=GEMINI_MODEL, contents=prompt)`
  Token counts: `response.usage_metadata.prompt_token_count` and
  `response.usage_metadata.candidates_token_count`
- Gemini 2.5 Flash pricing changes periodically. Verify current rates at
  [Google AI pricing](https://ai.google.dev/pricing) before committing the
  constants. Use thinking-disabled pricing if thinking tokens are not needed.
- `ingest.py` should NOT re-implement pipeline logic — it calls the functions
  already exported by features 02–05. Its only job is orchestration and I/O
  formatting.
- The cost confirmation prompt in `ask.py` can use a rough estimate (e.g.
  assume ~2000 input tokens) rather than a real dry-run token count, since a
  real count would require an extra API call. Labelling it "estimated" is fine.
- Sources printed by `ask.py` should be deduplicated by URL (same URL can
  appear in multiple chunks); print each URL only once.
