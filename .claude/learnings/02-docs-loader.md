# Learnings: 02 — Docs Loader

---

## Why this feature exists

**What:** The docs loader is the first step of the RAG pipeline. It fetches all Stripe documentation and writes it to disk as a JSONL file.
**Why:** RAG (Retrieval-Augmented Generation) needs a text corpus before it can do anything. You can't chunk, embed, or retrieve docs that don't exist locally. Feature 02 creates that corpus — everything downstream depends on it.
**How:** One CLI run (`uv run python -m src.rag.loader`) produces `data/stripe_docs.jsonl`. Each line is one doc as `{"url": ..., "title": ..., "content": ...}`.

---

## llms.txt (Stripe's LLM-friendly index)

**What:** A plain-text Markdown file that lists all of a site's documentation, one link per line, with optional one-line descriptions. Defined by the llmstxt.org convention. Stripe publishes theirs at `https://docs.stripe.com/llms.txt`.
**Why:** It's the fastest way to discover every doc URL without scraping HTML or navigating a sitemap. Designed specifically for LLM tools that need a corpus.
**How:**
```
## Docs
- [Testing](https://docs.stripe.com/testing.md): Simulate payments to test your integration.
- [API Reference](https://docs.stripe.com/api.md)

## Payment Methods
- [Payment Methods API](https://docs.stripe.com/payments/payment-methods.md): Learn about the API...
```
`## H2` headers are section categories, not docs. Each `- [Title](URL)` list item is a doc. Some have descriptions after `:`, many don't. All URLs end in `.md`.

---

## llms-full.txt (the spec's original URL — does not exist for Stripe)

**What:** The spec assumed `https://docs.stripe.com/llms-full.txt` — a single file with all docs concatenated, separated by `---` delimiters. Other sites (e.g. Anthropic) publish this. Stripe does not.
**Why it matters:** The absence forced a different architecture — fetch the index first, then fetch each `.md` file individually. The format was inferred from Anthropic's reference implementation and the individual `.md` files.
**Anthropic's format (for reference):**
```
---

# Doc Title

URL: https://...

# Doc Title

Full content...

---
```

---

## Individual Stripe `.md` files

**What:** Each doc at `https://docs.stripe.com/<path>.md` is pure Markdown with no frontmatter. First line is always `# Title` (H1). Content follows immediately.
**Why it matters:** This means title extraction is simple (find the first `# ` line) and there's nothing to strip before the content.
**How a typical doc looks:**
```
# Testing

Simulate payments to test your integration.

## How to use test cards

When you work with a test card, use test API keys in all API calls.
```

---

## httpx — sync and async HTTP

**What:** A modern Python HTTP client that supports both synchronous and async modes. Already in `pyproject.toml`.
**Why:** `requests` only supports sync. `httpx` gives you `httpx.Client` for a simple single request and `httpx.AsyncClient` for parallel requests — same API, different context managers.
**How:**
```python
# Sync — single request
with httpx.Client(timeout=30.0) as client:
    resp = client.get(url)

# Async — parallel requests
async with httpx.AsyncClient(timeout=30.0) as client:
    resp = await client.get(url)
```
Key exceptions to catch: `httpx.TimeoutException` (request took too long).

---

## asyncio.gather + Semaphore — parallel fetching with a concurrency cap

**What:** `asyncio.gather(*tasks)` runs all async tasks concurrently. `asyncio.Semaphore(N)` limits how many run at the same time.
**Why:** Fetching 494 docs one-by-one would take minutes. Fetching all at once could hammer the server or exhaust connections. A semaphore of 20 is the middle ground — fast but polite.
**How:**
```python
sem = asyncio.Semaphore(20)

async def _fetch_one(client, sem, url):
    async with sem:          # blocks until a slot is free
        return await client.get(url)

results = await asyncio.gather(*[_fetch_one(client, sem, url) for url in urls])
```
`asyncio.gather` returns results in the same order as the input list, even though they complete out of order.

---

## asyncio.run — bridging sync and async

**What:** `asyncio.run(coroutine)` runs an async function from synchronous code and blocks until it's done.
**Why:** The public API (`fetch_all_docs`) is sync so callers don't need to think about event loops. The async work happens inside.
**How:**
```python
def fetch_all_docs(index: str) -> str:
    return asyncio.run(_async_fetch_all(index))   # sync entry point
```

---

## Custom string markers — assembling a parseable blob

**What:** Because individual `.md` files don't contain their own URL, `fetch_all_docs` prepends a unique HTML comment marker before each doc's content before joining them into one string.
**Why:** `parse_llms_txt` needs to receive a single string (its signature is `(raw: str) -> Iterator[dict]`) and needs to know which URL belongs to which body. An HTML comment like `<!-- stripe-doc-start: URL -->` cannot appear naturally in Markdown prose.
**How:**
```python
# Assembly (fetch_all_docs)
parts.append(f"<!-- stripe-doc-start: {url} -->\n{body}")
assembled = "\n\n".join(parts)

# Parsing (parse_llms_txt)
parts = re.compile(r"<!-- stripe-doc-start: ([^>]+) -->").split(assembled)
# → [preamble, url1, body1, url2, body2, ...]
```

---

## re.split with a capturing group

**What:** When you pass a regex with a capturing group `(...)` to `re.split()`, Python includes the captured text in the result list.
**Why:** This is the key trick that lets us split an assembled string into alternating `[url, body, url, body, ...]` without a second pass.
**How:**
```python
import re
pattern = re.compile(r"<!-- stripe-doc-start: ([^>]+) -->")
parts = pattern.split("...assembled text...")
# parts[0]  = text before first marker  (discard)
# parts[1]  = url1
# parts[2]  = body1
# parts[3]  = url2
# parts[4]  = body2 ...
for i in range(1, len(parts) - 1, 2):
    url  = parts[i]
    body = parts[i + 1]
```

---

## Generator (Iterator) — parse_llms_txt uses yield

**What:** `parse_llms_txt` is a generator function — it uses `yield` instead of building a list and returning it.
**Why:** The corpus is large (480 docs, some with hundreds of KB of content). Loading all records into memory at once before writing would waste RAM. A generator produces one record at a time, and `save_jsonl` writes each immediately.
**How:**
```python
def parse_llms_txt(raw: str) -> Iterator[dict]:
    ...
    for i in range(1, len(parts) - 1, 2):
        ...
        yield {"url": url, "title": title, "content": content}
```
The caller (or `save_jsonl`) drives iteration — records are produced only as needed.

---

## JSONL (JSON Lines) — the output format

**What:** One JSON object per line, newline-separated. File extension `.jsonl`. Each line is independently valid JSON.
**Why:** Streaming-friendly — you can read one record at a time without loading the whole file. Easy to `wc -l` to count records. Standard format for ML/RAG datasets.
**How:**
```python
with path.open("w", encoding="utf-8") as fh:
    for doc in docs:
        fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
```
`ensure_ascii=False` keeps non-ASCII characters (em dashes, accented letters) readable rather than `\u`-escaped.

---

## dict.fromkeys — stable deduplication

**What:** `dict.fromkeys(iterable)` creates a dict where keys are the iterable's items. Since dict keys are unique and insertion-ordered in Python 3.7+, this deduplicates while preserving the original order.
**Why:** `llms.txt` occasionally lists the same URL in multiple sections. Fetching a URL twice wastes a request.
**How:**
```python
pairs = list(dict.fromkeys(_INDEX_URL_RE.findall(index)))
# findall returns [(title, url), ...] — dict.fromkeys deduplicates by (title, url) tuple
```

---

## Record validation and drop rules

**What:** `parse_llms_txt` silently drops records that don't meet quality thresholds, logging a warning for each.
**Why:** Some Stripe `.md` URLs are stub pages, redirect targets, or fragment-anchored links with no real content. Passing bad records downstream would corrupt the RAG corpus.
**Rules applied:**
- URL must be non-empty and start with `https://docs.stripe.com` → else drop
- Body must contain at least one `# H1` line → else drop (no title)
- `content` (full body, stripped) must be ≥ 50 characters → else drop
- Non-200 HTTP responses during batch fetch → skip at fetch time, never reach parser

---

## data/ directory and .gitignore

**What:** Output is written to `data/stripe_docs.jsonl`. The `data/` directory is already in `.gitignore` and is created at runtime by `save_jsonl`.
**Why:** The JSONL file is a large derived artifact (~hundreds of MB uncompressed). It's regenerated on demand — no reason to commit it.
**How:** `path.parent.mkdir(parents=True, exist_ok=True)` before opening the file ensures the directory exists even on a fresh clone.
