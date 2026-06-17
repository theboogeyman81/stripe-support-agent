# Spec 03 — Chunker

## Feature
Split each doc in `data/stripe_docs.jsonl` into smaller, retrieval-sized
text chunks suitable for embedding. Write chunks to `data/stripe_chunks.jsonl`.

## Why
Embedding entire docs is useless for retrieval — a 263 KB doc becomes
one vector that represents an average of everything in it. Chunking
into ~500-token pieces means each chunk is about one concept, so
embedding similarity will actually surface the relevant section, not
just the relevant document.

## Input contract
File: `data/stripe_docs.jsonl`
Each line: `{"url": str, "title": str, "content": str}`

## Output contract
File: `data/stripe_chunks.jsonl`
Each line:
```json
{
  "chunk_id": "stripe-<sha1(url)[:8]>-<chunk_index>",
  "doc_url": "https://docs.stripe.com/...",
  "doc_title": "Doc title",
  "chunk_index": 0,
  "text": "The chunk's text content",
  "token_count": 487
}
```

Field rules:
- `chunk_id` is unique across the whole file
- `chunk_index` is 0-based, increments per doc
- `token_count` is the actual measured token count of `text`
- `text` is non-empty, stripped

## Chunking strategy
- Target chunk size: **500 tokens**
- Overlap between consecutive chunks: **50 tokens**
- Tokenizer: `tiktoken` with `cl100k_base` encoding
  (Gemini doesn't expose its tokenizer publicly; cl100k_base is a reasonable
  proxy for sizing. We're not using tokens for billing here, just for splitting.)
- Splitting approach: **recursive character splitting** that prefers to split
  on these separators in order: `\n\n`, `\n`, `. `, ` `, `""`
  This keeps semantic units (paragraphs, sentences) intact where possible.
- Do NOT split mid-code-block if avoidable. Code blocks are delimited by
  triple backticks in markdown. Treat a triple-backtick block as a unit;
  if a code block is larger than 500 tokens, allow it to exceed the limit
  rather than splitting it in the middle.

## Scope (in)
- `src/rag/chunker.py` with:
  - `count_tokens(text: str) -> int` — uses tiktoken
  - `chunk_text(text: str, target_tokens: int = 500, overlap_tokens: int = 50) -> list[str]`
  - `chunk_doc(doc: dict) -> Iterator[dict]` — takes one doc, yields chunk records
  - `chunk_corpus(input_path: Path, output_path: Path) -> dict` — reads JSONL, writes JSONL, returns stats
- CLI entry: `python -m src.rag.chunker` reads `data/stripe_docs.jsonl`,
  writes `data/stripe_chunks.jsonl`, prints stats
- Stats printed:
  - Total docs processed
  - Total chunks produced
  - Average chunks per doc
  - Min / median / max chunks per doc
  - Min / median / max token count per chunk
  - Time elapsed
- Tests in `tests/test_chunker.py`:
  - `count_tokens` returns a sensible number for a known string
  - `chunk_text` on a short string returns 1 chunk
  - `chunk_text` on a long string returns multiple chunks with the right overlap
  - `chunk_doc` produces records with all required fields and correct chunk_index sequence
  - Code blocks (triple-backtick) are not split mid-block

## Scope (out)
- Embeddings (next feature)
- Reranking
- Metadata enrichment beyond url/title
- Multilingual handling
- Header-based chunking (e.g., split by markdown `##` headers) — interesting but
  more complex; stick with recursive char splitting for v1

## Dependencies
- New: `tiktoken`
- Existing: stdlib only otherwise

## Acceptance criteria
1. `uv run python -m src.rag.chunker` completes without error
2. `data/stripe_chunks.jsonl` exists with > 480 lines (more chunks than docs)
3. Median chunk token count is between 300 and 600
4. Max chunk token count ≤ 1500 (allows code-block overflow but flags pathological cases)
5. Every chunk has all required fields and non-empty text
6. Chunk IDs are unique across the whole file
7. For the largest doc (testing.md, 263 KB), it produces a sensible number
   of chunks (rough check: 263 KB ≈ ~65k tokens ≈ ~130 chunks at 500 tokens)
8. `uv run pytest tests/test_chunker.py` passes
9. `uv run ruff check src/rag/chunker.py` passes

## Failure modes to handle
- Empty doc content: skip with warning
- Doc with content shorter than target_tokens: produces 1 chunk, that's fine
- Malformed JSON line in input: skip with warning, do not crash

## Notes
- 500/50 is a starting point. We may revisit after retrieval quality evaluation
  in a later phase. Do not over-tune now.
- We're using tiktoken's cl100k_base as a *proxy* for Gemini's tokenizer.
  This is fine for sizing decisions. It would not be fine for billing.