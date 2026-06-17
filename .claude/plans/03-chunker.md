# Plan: Spec 03 — Chunker

## Context

Phase 1, Feature 03. The corpus (`data/stripe_docs.jsonl`) exists. Each record is
`{"url", "title", "content"}` where `content` is the full raw Markdown of the doc.
The chunker splits each `content` into ~500-token pieces, adds overlap for context
continuity, and writes `data/stripe_chunks.jsonl`.

Input shape observed from `data/stripe_docs.jsonl`:
```json
{
  "url": "https://docs.stripe.com/testing.md",
  "title": "Testing",
  "content": "# Testing\n\nSimulate payments to test your integration.\n\n## How to use test cards\n\n..."
}
```

---

## 1. Recursive Character Splitting — Algorithm (Step by Step)

### Phase 0: Module-level singleton

```python
import tiktoken
_ENC = tiktoken.get_encoding("cl100k_base")
```

Constructed once at import time. All encode/decode calls go through `_ENC` to avoid
re-initialising the BPE tables on every call.

---

### Phase 1: Partition text into prose segments and code blocks

The spec says: do not split mid-code-block. Code blocks are delimited by triple
backticks. The first step is to identify them so the recursive splitter never touches
their internals.

```python
import re
_CODE_FENCE_RE = re.compile(r"(```[\s\S]*?```)")
```

`re.split` with a capturing group returns alternating `[prose, code, prose, code, ...]`.
Even-indexed elements are prose; odd-indexed elements are the captured code blocks.

```python
def _segments(text: str) -> list[tuple[bool, str]]:
    parts = _CODE_FENCE_RE.split(text)
    result = []
    for i, part in enumerate(parts):
        if not part:
            continue
        result.append((i % 2 == 1, part))   # True → code block
    return result
```

Example: `"Prose\n\n```python\nx=1\n```\nMore prose"` →
```
[(False, "Prose\n\n"), (True, "```python\nx=1\n```"), (False, "\nMore prose")]
```

---

### Phase 2: Recursively split prose into atoms ≤ target_tokens

Each prose segment is split into the smallest possible pieces that still fit within
`target_tokens`. Code blocks are never passed to this phase.

Separator priority (spec): `"\n\n"`, `"\n"`, `". "`, `" "`, `""` (character level).

```python
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

def _split_prose(text: str, target: int) -> list[str]:
    if count_tokens(text) <= target:
        return [text] if text.strip() else []
    for sep in _SEPARATORS:
        if sep == "":
            return [text]          # Can't split further; accept oversized atom
        if sep not in text:
            continue
        raw_pieces = text.split(sep)
        atoms: list[str] = []
        for j, piece in enumerate(raw_pieces):
            # Re-attach separator to end of each piece (except last) so that
            # paragraph/sentence boundaries survive the pack-and-merge step.
            rejoined = (piece + sep) if j < len(raw_pieces) - 1 else piece
            atoms.extend(_split_prose(rejoined, target))
        return atoms
    return [text]
```

Why re-attach the separator: without it, `"Para A\n\nPara B"` → `["Para A", "Para B"]`
and when repacked into one chunk they'd be concatenated without any whitespace. By keeping
`"Para A\n\n"` and `"Para B"` as atoms, the final decoded chunk preserves the blank line.

---

### Phase 3: Build the ordered atom list

Combine results from Phases 1 and 2 into a single ordered sequence:

```python
atoms: list[tuple[bool, str]] = []   # (is_code_block, text)

for is_code, seg in _segments(text):
    if is_code:
        atoms.append((True, seg))
    else:
        for atom in _split_prose(seg, target_tokens):
            atoms.append((False, atom))
```

At this point each non-code atom is guaranteed ≤ `target_tokens` tokens. Code atoms may
exceed `target_tokens` (the spec allows code blocks to overflow).

---

### Phase 4: Greedy packing with token-level overlap

Maintain a buffer of raw token IDs (`list[int]`). Token IDs are integers from tiktoken's
vocabulary. Working at the token ID level lets us slice the overlap exactly.

```
cur_ids: list[int] = []
chunks: list[str] = []

for (is_code, atom) in atoms:
    atom_ids = _ENC.encode(atom)

    # --- Large code block (overflow case) ---
    if is_code and len(atom_ids) > target_tokens:
        if cur_ids:
            chunks.append(_ENC.decode(cur_ids))
            cur_ids = []
        chunks.append(atom)        # emitted as-is, no overlap
        continue

    # --- Normal atom: would overflow current buffer ---
    if cur_ids and len(cur_ids) + len(atom_ids) > target_tokens:
        chunks.append(_ENC.decode(cur_ids))
        overlap_ids = cur_ids[-overlap_tokens:]      # last N token IDs
        cur_ids = overlap_ids + atom_ids

    # --- Fits in current buffer ---
    else:
        cur_ids.extend(atom_ids)

# Flush remainder
if cur_ids:
    chunks.append(_ENC.decode(cur_ids))

return [c.strip() for c in chunks if c.strip()]
```

**Why this preserves code-block integrity:** code blocks are never passed to
`_split_prose`, so they arrive as a single atom. If a code block fits within the
current buffer, it's packed normally. If it would overflow, it's flushed out alone.
Either way its internal content is never touched.

---

## 2. Token-Level Overlap Measurement

tiktoken encodes text as a list of integer token IDs:

```python
ids: list[int] = _ENC.encode("Hello, world!")   # e.g. [9906, 11, 1917, 0]
```

To carry over exactly 50 tokens of overlap from the previous chunk:

```python
overlap_ids = cur_ids[-50:]             # slice the last 50 token IDs
next_start = overlap_ids + atom_ids     # prepend to new chunk
```

When the chunk is later decoded:

```python
chunk_text = _ENC.decode(cur_ids)       # list[int] → str
```

`_ENC.decode` converts each integer ID back to its byte sequence via the BPE vocabulary
and concatenates them. Slicing token IDs is exact — no character-level approximation,
no risk of splitting a multi-byte Unicode character mid-sequence (token boundaries
are always byte-aligned by construction in tiktoken).

The `count_tokens` function:

```python
def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))
```

---

## 3. `chunk_text` Return Value and `chunk_doc` Consumption

### `chunk_text` signature and return value

```python
def chunk_text(text: str, target_tokens: int = 500, overlap_tokens: int = 50) -> list[str]
```

Returns a **flat list of strings**. Each string is one chunk's full text, ready to be
embedded. Properties:
- Length ≥ 1 (even a short doc produces 1 chunk)
- Each element is `.strip()`-ped and non-empty
- Consecutive elements share the last `overlap_tokens` tokens at their boundary
  (i.e., `chunk[i]` ends with the same token sequence that `chunk[i+1]` begins with)
- Code blocks that overflow `target_tokens` appear as their own element and are not
  subject to the overlap rule (no overlap prefix or suffix around a large code block)

### `chunk_doc` and how it consumes `chunk_text`

```python
import hashlib
from collections.abc import Iterator

def chunk_doc(doc: dict) -> Iterator[dict]:
    url     = doc["url"]
    title   = doc["title"]
    content = doc.get("content", "").strip()
    if not content:
        log.warning("chunk_doc: empty content for %s — skipped", url)
        return

    url_hash = hashlib.sha1(url.encode()).hexdigest()[:8]
    for i, text in enumerate(chunk_text(content)):
        yield {
            "chunk_id":    f"stripe-{url_hash}-{i}",
            "doc_url":     url,
            "doc_title":   title,
            "chunk_index": i,
            "text":        text,
            "token_count": count_tokens(text),
        }
```

`chunk_doc` iterates over the `list[str]` from `chunk_text`, wraps each string in the
output schema, and yields. It never builds the full list of chunk dicts in memory (it's
a generator). The `chunk_index` is simply the enumeration index over `chunk_text`'s
output — it always starts at 0 and increments by 1.

### `chunk_corpus` and the `__main__` block

```python
import json, statistics, time
from pathlib import Path

INPUT_PATH  = Path("data/stripe_docs.jsonl")
OUTPUT_PATH = Path("data/stripe_chunks.jsonl")

def chunk_corpus(input_path: Path, output_path: Path) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    docs_processed = 0
    chunks_per_doc: list[int] = []
    token_counts:   list[int] = []

    with (
        input_path.open(encoding="utf-8") as fin,
        output_path.open("w", encoding="utf-8") as fout,
    ):
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("skip malformed JSON line: %s", exc)
                continue
            doc_chunks = list(chunk_doc(doc))
            for chunk in doc_chunks:
                fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            docs_processed += 1
            chunks_per_doc.append(len(doc_chunks))
            token_counts.extend(c["token_count"] for c in doc_chunks)

    elapsed = time.perf_counter() - t0
    return {
        "docs":          docs_processed,
        "chunks":        sum(chunks_per_doc),
        "avg_per_doc":   statistics.mean(chunks_per_doc) if chunks_per_doc else 0,
        "min_per_doc":   min(chunks_per_doc, default=0),
        "median_per_doc":statistics.median(chunks_per_doc) if chunks_per_doc else 0,
        "max_per_doc":   max(chunks_per_doc, default=0),
        "min_tokens":    min(token_counts, default=0),
        "median_tokens": statistics.median(token_counts) if token_counts else 0,
        "max_tokens":    max(token_counts, default=0),
        "elapsed_s":     round(elapsed, 1),
    }
```

---

## 4. Test Cases

File: `tests/test_chunker.py`. No network calls; no file I/O except where `tmp_path`
is used.

### Setup / shared constants

```python
import tiktoken
import pytest
from src.rag.chunker import count_tokens, chunk_text, chunk_doc

_ENC = tiktoken.get_encoding("cl100k_base")

# ~10 tokens per sentence: "The quick brown fox jumps over the lazy dog. "
SENTENCE = "The quick brown fox jumps over the lazy dog. "
```

---

### Test 1 — `test_count_tokens_known_string`

```python
def test_count_tokens_known_string():
    n = count_tokens("Hello, world!")
    # cl100k_base: "Hello" + "," + " world" + "!" = 4 tokens
    assert isinstance(n, int)
    assert 2 <= n <= 8    # range guards against tokenizer change, not exact
```

Why: verifies the function runs and produces a plausible integer without asserting a
fragile exact count.

---

### Test 2 — `test_chunk_text_short_returns_one_chunk`

```python
def test_chunk_text_short_returns_one_chunk():
    short = "This is a short sentence about Stripe payments."
    chunks = chunk_text(short)
    assert len(chunks) == 1
    assert "short sentence" in chunks[0]
```

Input is well under 500 tokens (~10 tokens). Expected: exactly one chunk returned,
containing the original text.

---

### Test 3 — `test_chunk_text_long_returns_multiple_chunks`

```python
def test_chunk_text_long_returns_multiple_chunks():
    # SENTENCE ≈ 10 tokens; 150 × = ~1500 tokens → should produce ≥ 3 chunks at 500t
    long_text = SENTENCE * 150
    chunks = chunk_text(long_text, target_tokens=500, overlap_tokens=50)
    assert len(chunks) >= 3
    for chunk in chunks:
        # Each chunk fits within limit (code-block overflow not applicable here)
        assert count_tokens(chunk) <= 550   # slight slack for separator tokens
```

---

### Test 4 — `test_chunk_text_overlap_is_token_exact`

```python
def test_chunk_text_overlap_is_token_exact():
    long_text = SENTENCE * 200    # ~2000 tokens
    chunks = chunk_text(long_text, target_tokens=500, overlap_tokens=50)
    assert len(chunks) >= 2

    ids0 = _ENC.encode(chunks[0])
    ids1 = _ENC.encode(chunks[1])

    # The last 50 token IDs of chunk 0 must equal the first 50 of chunk 1
    overlap = ids0[-50:]
    assert ids1[:50] == overlap
```

Why: this is the only test that directly validates the token-level overlap contract.
Verifying at the token-ID list level (not character level) is exact.

---

### Test 5 — `test_chunk_doc_fields_and_index_sequence`

```python
def test_chunk_doc_fields_and_index_sequence():
    doc = {
        "url":     "https://docs.stripe.com/test.md",
        "title":   "Test Doc",
        "content": SENTENCE * 200,
    }
    chunks = list(chunk_doc(doc))
    assert len(chunks) >= 2

    for i, chunk in enumerate(chunks):
        assert chunk["chunk_id"].startswith("stripe-")
        assert chunk["chunk_id"].endswith(f"-{i}")
        assert chunk["doc_url"]   == "https://docs.stripe.com/test.md"
        assert chunk["doc_title"] == "Test Doc"
        assert chunk["chunk_index"] == i
        assert chunk["text"] and chunk["text"].strip()
        assert isinstance(chunk["token_count"], int) and chunk["token_count"] > 0
```

---

### Test 6 — `test_chunk_doc_unique_ids`

```python
def test_chunk_doc_unique_ids():
    doc = {
        "url":     "https://docs.stripe.com/test.md",
        "title":   "Test Doc",
        "content": SENTENCE * 200,
    }
    ids = [c["chunk_id"] for c in chunk_doc(doc)]
    assert len(ids) == len(set(ids))
```

---

### Test 7 — `test_code_block_not_split`

```python
def test_code_block_not_split():
    # Build a code block that exceeds 500 tokens so the splitter MUST handle it.
    # "result = some_function(argument_one, argument_two, argument_three)  # x\n"
    # is ~17 tokens; 40 lines ≈ 680 tokens.
    code_line  = "result = some_function(argument_one, argument_two, argument_three)  # x\n"
    code_block = "```python\n" + code_line * 40 + "```"
    text = "Prose before the code block.\n\n" + code_block + "\n\nProse after the code block."

    chunks = chunk_text(text)

    # Every chunk must have an even number of ``` markers.
    # An odd count means a code fence was split across chunks.
    for chunk in chunks:
        fence_count = chunk.count("```")
        assert fence_count % 2 == 0, (
            f"Code block was split: found {fence_count} ``` in chunk:\n{chunk[:200]}"
        )
```

Exact input chosen so `code_block` alone is ~700 tokens — clearly above 500. The prose
segments are short (~10 tokens each) so they'll pack without interference. The only
interesting behaviour is how the code block is handled.

---

## 5. Files to Create or Modify

| File | Action | Notes |
|---|---|---|
| `src/rag/chunker.py` | Implement | `count_tokens`, `chunk_text`, `chunk_doc`, `chunk_corpus`, `__main__` block, module-level `_ENC` singleton |
| `tests/test_chunker.py` | Create | 7 tests, no network, no disk I/O except `tmp_path` |
| `pyproject.toml` | Modify | Add `"tiktoken"` to `[project] dependencies` |

No other files require changes. `data/` is already in `.gitignore` and is created at
runtime by `chunk_corpus`.

---

## 6. PowerShell Verification Commands (Acceptance Criteria)

```powershell
# AC 1 — CLI completes without error
uv run python -m src.rag.chunker

# AC 2 — more than 480 lines (more chunks than docs)
(Get-Content data/stripe_chunks.jsonl | Measure-Object -Line).Lines

# AC 3 — median token count between 300 and 600
$counts = Get-Content data/stripe_chunks.jsonl |
    ForEach-Object { ($_ | ConvertFrom-Json).token_count } |
    Sort-Object
$counts[[int]($counts.Count / 2)]

# AC 4 — max token count ≤ 1500
($counts | Measure-Object -Maximum).Maximum

# AC 5 — every chunk has all required fields and non-empty text
$bad = Get-Content data/stripe_chunks.jsonl | ForEach-Object {
    $c = $_ | ConvertFrom-Json
    if (-not $c.chunk_id -or -not $c.doc_url -or -not $c.doc_title `
        -or $null -eq $c.chunk_index -or -not $c.text -or -not $c.token_count) {
        $_
    }
}
if ($bad) { Write-Error "Bad chunks found"; $bad | Select-Object -First 3 }
else       { "All chunks valid" }

# AC 6 — chunk IDs are unique across the whole file
$ids = Get-Content data/stripe_chunks.jsonl |
    ForEach-Object { ($_ | ConvertFrom-Json).chunk_id }
$unique = ($ids | Sort-Object -Unique).Count
if ($unique -eq $ids.Count) { "IDs unique: $unique" } else { Write-Error "Duplicate IDs found" }

# AC 7 — testing.md chunk count sanity check (~130 expected for a 263 KB doc)
$testChunks = Get-Content data/stripe_chunks.jsonl |
    Where-Object { ($_ | ConvertFrom-Json).doc_url -like "*testing.md*" }
"testing.md produced $($testChunks.Count) chunks (expected ~130)"

# AC 8 — all tests pass
uv run pytest tests/test_chunker.py -v

# AC 9 — ruff clean
uv run ruff check src/rag/chunker.py
```

---

## Constants (top of `chunker.py`)

```python
import tiktoken

_ENC        = tiktoken.get_encoding("cl100k_base")
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

INPUT_PATH  = Path("data/stripe_docs.jsonl")
OUTPUT_PATH = Path("data/stripe_chunks.jsonl")
```

---

## Edge Cases and How They're Handled

| Case | Handling |
|---|---|
| Doc `content` is empty string | `chunk_doc` logs warning and returns (yields nothing) |
| Doc shorter than 500 tokens | `chunk_text` returns a single-element list; 1 chunk per doc |
| Code block ≤ 500 tokens | Packed normally alongside prose atoms; no special treatment |
| Code block > 500 tokens | Flushed as its own chunk; no overlap prefix/suffix around it |
| Malformed JSON line in input | `chunk_corpus` catches `json.JSONDecodeError`, logs warning, skips |
| Adjacent code blocks with no prose between | Each is its own atom; both enter the packing loop and are handled independently |
| `data/stripe_chunks.jsonl` parent dir missing | `output_path.parent.mkdir(parents=True, exist_ok=True)` in `chunk_corpus` |
