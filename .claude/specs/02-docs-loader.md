# Spec 02 — Docs Loader

## Feature
Fetch Stripe's LLM-friendly documentation bundle and parse it into a
JSONL file where each line is one logical doc record.

## Why
RAG needs a corpus on disk before any chunking, embedding, or retrieval
can happen. Stripe publishes `llms-full.txt` — a single text file
containing all their docs in an LLM-friendly format. Using this avoids
HTML scraping, sitemap crawling, and rate-limit handling.

## Source
- URL: https://docs.stripe.com/llms-full.txt
- Format: plain text, multiple docs concatenated with delimiters
  (exact format to be inspected before parser is written)

## Output contract
File: `data/stripe_docs.jsonl`
One JSON object per line:
```json
{
  "url": "https://docs.stripe.com/...",
  "title": "Doc title",
  "content": "Full markdown/text body of the doc"
}
```

Field rules:
- `url`: non-empty string, must start with `https://docs.stripe.com`
- `title`: non-empty string, stripped of leading/trailing whitespace
- `content`: non-empty string, at least 50 characters after stripping
- Records with empty content or missing url are dropped (with a warning log)

## Scope (in)
- `src/rag/loader.py` with three functions:
  - `fetch_stripe_docs(url: str) -> str` — HTTP GET via httpx, 30s timeout, raise on non-200
  - `parse_llms_txt(raw: str) -> Iterator[dict]` — yields doc dicts
  - `save_jsonl(docs: Iterable[dict], path: Path) -> int` — writes JSONL, returns count
- CLI entry: `python -m src.rag.loader` runs fetch → parse → save → print count
- One test in `tests/test_loader.py` covering `parse_llms_txt` with an inline sample string (no network)

## Scope (out)
- Chunking
- Embedding
- Incremental/delta loading (always full refresh in Phase 1)
- HTML parsing (we're using llms-full.txt specifically to avoid this)
- Retry logic, exponential backoff (one attempt is fine for now)

## Behaviour
- Parser must inspect the actual format of llms-full.txt before being
  written. Format observations must be documented in a comment at the
  top of `parse_llms_txt`.
- Parser yields records (generator), does not build full list in memory.
- Loader prints progress: "Fetched N bytes", "Parsed N docs",
  "Wrote N docs to <path>".
- Dropped records (empty content, missing url) print a warning with reason.

## Dependencies
- `httpx` — already in pyproject.toml from Feature 1
- No new deps

## Acceptance criteria
1. `uv run python -m src.rag.loader` completes without error
2. `data/stripe_docs.jsonl` exists and is non-empty
3. `(Get-Content data/stripe_docs.jsonl | Measure-Object -Line).Lines` returns >= 100
   (Stripe has hundreds of docs; if we get <100, parser is wrong)
4. First record inspected manually has all three fields populated and
   content is real markdown, not a header or empty string
5. `uv run pytest tests/test_loader.py` passes
6. `uv run ruff check src/rag/loader.py` passes
7. No network call in any test

## Failure modes to handle explicitly
- HTTP non-200: raise with status code and URL in message
- Empty response body: raise ValueError("Empty response from Stripe")
- Malformed records during parsing: skip with warning, do not crash

## Notes
- The parser format is the highest-risk part of this feature. Inspect
  before implementing.
- Do not commit `data/stripe_docs.jsonl` (already in .gitignore).
- Add a `last_updated` field? No — keep schema minimal in Phase 1.