# Plan: Spec 02 — Docs Loader

## Context

Phase 1, Feature 02. The RAG pipeline needs a corpus of Stripe documentation on disk before chunking, embedding, or retrieval can happen. The spec assumes a single `llms-full.txt` file at `https://docs.stripe.com/llms-full.txt`, but that URL returns **HTTP 404** — Stripe has not published it.

What Stripe *does* publish:
- `https://docs.stripe.com/llms.txt` — a Markdown index listing every doc URL + one-line description
- `https://docs.stripe.com/<path>.md` — individual docs, full Markdown content

The approved approach (**Option 2**): fetch `llms.txt` to discover URLs, then batch-fetch each `.md` file in parallel using `httpx.AsyncClient`. This delivers full doc bodies while staying within the Phase 1 constraint of no HTML scraping.

---

## Format Observations (required by spec)

### `llms.txt` (index) — `https://docs.stripe.com/llms.txt`
```
# Stripe Documentation
[preamble note about npm versions]

## Docs
- [Testing](https://docs.stripe.com/testing.md): Simulate payments to test your integration.
- [API Reference](https://docs.stripe.com/api.md)
- [Receive payouts](https://docs.stripe.com/payouts.md): Set up your bank account to receive payouts.

## Payment Methods
Acquire more customers and improve conversion...

- [Payment Methods API](https://docs.stripe.com/payments/payment-methods.md): Learn about the API...
```

Key points:
- `## H2` headers separate topic sections (not individual docs)
- List items: `- [Title](URL)` or `- [Title](URL): description`
- Some entries have no description (e.g., `[API Reference]`)
- All doc URLs end in `.md`, base is `https://docs.stripe.com`

### Individual `.md` files — e.g., `https://docs.stripe.com/testing.md`
```
# Testing

Simulate payments to test your integration.

## How to use test cards

When you work with a test card, use test API keys...
```

Key points:
- No YAML frontmatter — content starts immediately
- First line is always `# Title` (H1 Markdown header)
- No source URL annotation within the file itself
- Pure Markdown: headings, bullet lists, tables, fenced code blocks

### Reference `llms-full.txt` format (Anthropic implementation, for reference)
```
---

# Get started with Claude

URL: https://platform.claude.com/docs/en/get-started

# Get started with Claude

Make your first API call...

---
```
Uses `---` as delimiter with `URL:` line per doc. Stripe's individual `.md` files follow the same per-doc pattern but without the delimiter or URL annotation.

---

## Implementation Plan

### Function architecture

| Function | Signature | Role |
|---|---|---|
| `fetch_stripe_docs` | `(url: str) -> str` | GET `llms.txt`, raise on non-200 or empty |
| `fetch_all_docs` | `(index: str) -> str` | Extract URLs from index, async batch-fetch each `.md`, assemble into parseable string |
| `parse_llms_txt` | `(raw: str) -> Iterator[dict]` | Parse assembled string → yield `{url, title, content}` records |
| `save_jsonl` | `(docs: Iterable[dict], path: Path) -> int` | Write JSONL, return count |

The `__main__` block chains them:
```python
raw_index = fetch_stripe_docs(LLMS_TXT_URL)
full_raw   = fetch_all_docs(raw_index)
docs       = parse_llms_txt(full_raw)
n          = save_jsonl(docs, OUTPUT_PATH)
```

---

### Parser strategy

`fetch_all_docs` assembles doc content using a custom marker that cannot appear in Markdown prose:

```
<!-- stripe-doc-start: https://docs.stripe.com/testing.md -->
# Testing

Simulate payments to test your integration.

## How to use test cards
...

<!-- stripe-doc-start: https://docs.stripe.com/api.md -->
# API Reference

The Stripe API is organized around REST.
...
```

`parse_llms_txt` splits on the regex `<!-- stripe-doc-start: ([^>]+) -->` (using `re.split` with a capturing group):
- Odd-indexed chunks = URL strings
- Even-indexed chunks (starting at index 2) = doc text bodies
- Pair each URL with its body text

### URL extraction (inside `fetch_all_docs`)

Regex over `llms.txt`:
```python
re.findall(r'\[([^\]]+)\]\((https://docs\.stripe\.com/[^)]+\.md)\)', index)
```
Returns `(title, url)` pairs. Title from the index is used as a fallback if the `.md` body is missing its H1.

### Title extraction (inside `parse_llms_txt`)

For each doc chunk, find the first line matching `^# (.+)$` (multiline). Strip the `# ` prefix. If no H1 found, fall back to the URL path segment.

### Content field

`content` = the full text of the `.md` file body (including the H1 title line). Strip leading/trailing whitespace. Minimum 50 chars required; shorter records are dropped with a warning.

---

### Edge cases observed / handled

| Case | Handling |
|---|---|
| `llms.txt` entries with no description | Fine — we fetch the `.md` anyway; description is not used for content |
| `.md` fetch returns non-200 | Log warning with URL + status, skip (do not crash) |
| `.md` fetch times out | Caught as `httpx.TimeoutException`, logged as warning, skipped |
| Content < 50 chars after strip | Drop with warning "content too short" |
| Missing or empty URL in assembled format | Drop with warning "missing url" |
| Semaphore overload | Cap concurrent requests at 20 with `asyncio.Semaphore(20)` |
| `data/` directory doesn't exist | `path.parent.mkdir(parents=True, exist_ok=True)` in `save_jsonl` |
| Duplicate URLs in `llms.txt` | `dict.fromkeys` preserves order and deduplicates before fetching |
| Non-Stripe URL in index | Filtered by regex (only `https://docs.stripe.com/...md` accepted) |

---

### Test sample design (`tests/test_loader.py`)

Inline constant — no network call:

```python
SAMPLE_RAW = """\
<!-- stripe-doc-start: https://docs.stripe.com/testing.md -->
# Testing

Simulate payments to test your integration.

## How to use test cards

When you work with a test card, use test API keys in all API calls.

<!-- stripe-doc-start: https://docs.stripe.com/api.md -->
# API Reference

The Stripe API is organized around REST. Our API has predictable
resource-oriented URLs, accepts form-encoded request bodies, returns
JSON-encoded responses, and uses standard HTTP response codes.

<!-- stripe-doc-start: https://docs.stripe.com/stub.md -->
# Stub

"""
```

Tests to write:
- `test_yields_correct_count` — two records (stub dropped, content < 50 chars)
- `test_first_record_fields` — url / title / content values on the Testing doc
- `test_drops_short_content` — `stub.md` URL not in results
- `test_content_includes_title_line` — content starts with `# Testing`
- `test_save_jsonl_writes_and_returns_count` — uses `tmp_path`, no network

---

## Files to create / modify

| File | Action |
|---|---|
| `src/rag/loader.py` | Implement all four functions + `__main__` block |
| `tests/test_loader.py` | Create; 5 tests covering `parse_llms_txt` and `save_jsonl` |

`data/` directory: created at runtime by `save_jsonl`; already in `.gitignore`.

No new dependencies — `httpx` is already in `pyproject.toml`.

---

## Constants (top of `loader.py`)

```python
LLMS_TXT_URL = "https://docs.stripe.com/llms.txt"
OUTPUT_PATH  = Path("data/stripe_docs.jsonl")
_CONCURRENCY = 20
_TIMEOUT     = 30.0
```

---

## Verification — acceptance criteria from spec

```powershell
# 1. CLI completes without error
uv run python -m src.rag.loader

# 2. Output file exists and is non-empty
Test-Path data/stripe_docs.jsonl

# 3. At least 100 records
(Get-Content data/stripe_docs.jsonl | Measure-Object -Line).Lines

# 4. First record has all three fields with real content
Get-Content data/stripe_docs.jsonl | Select-Object -First 1 | ConvertFrom-Json

# 5. Tests pass (no network)
uv run pytest tests/test_loader.py -v

# 6. Ruff clean
uv run ruff check src/rag/loader.py

# 7. Confirm no network in tests (structural — mock is not used, sample is inline string)
uv run pytest tests/test_loader.py --tb=short
```
