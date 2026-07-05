# Learnings: 03 — Chunker

---

## Why this feature exists

**What:** The chunker splits each doc's full Markdown body into ~500-token pieces with 50-token overlap, writing `data/stripe_chunks.jsonl`.
**Why:** Embedding an entire doc produces one vector that averages everything in it — a 263 KB doc like `testing.md` would embed as a blur of every topic it covers. Splitting into ~500-token chunks means each vector represents roughly one concept, so similarity search surfaces the relevant section instead of just the relevant document.
**How:** `uv run python -m src.rag.chunker` reads `data/stripe_docs.jsonl` → writes `data/stripe_chunks.jsonl`, one line per chunk: `{"chunk_id", "doc_url", "doc_title", "chunk_index", "text", "token_count"}`.

---

## tiktoken as a sizing proxy, not a billing tool

**What:** Chunk sizes are measured in tokens via `tiktoken.get_encoding("cl100k_base")`, constructed once as a module-level singleton (`_ENC`).
**Why:** Gemini doesn't expose its own tokenizer publicly, so cl100k_base (OpenAI's) is used purely as a consistent way to measure "how much text is this" for splitting decisions. It would not be an accurate stand-in if the goal were billing/cost tracking — only relative sizing matters here.
**How:**
```python
_ENC = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))
```
Constructing `_ENC` once at import avoids re-initializing BPE tables on every call — significant when chunking hundreds of docs.

---

## Code-fence-aware segmentation with `re.split` + capturing group

**What:** Before any prose splitting happens, the raw text is partitioned into `(is_code_block, segment)` pairs so triple-backtick code blocks are never touched by the recursive splitter.
**Why:** Splitting mid-code-block would produce chunks with dangling, unbalanced ``` fences — useless and confusing for retrieval/display.
**How:**
```python
_CODE_FENCE_RE = re.compile(r"(```[\s\S]*?```)")

def _segments(text: str) -> list[tuple[bool, str]]:
    parts = _CODE_FENCE_RE.split(text)
    result = []
    for i, part in enumerate(parts):
        if part:
            result.append((i % 2 == 1, part))   # odd index = captured code block
    return result
```
Same `re.split`-with-capturing-group trick used in the loader (see [[02-docs-loader]]) — the capture group makes matched text appear in the output list at odd indices, alternating with the surrounding prose.

---

## Recursive separator splitting — and the infinite recursion bug

**What:** `_split_prose` recursively splits prose into atoms ≤ target tokens, trying separators in priority order: `\n\n`, `\n`, `. `, `" "`, then character-level (`""`).
**Why it recurses:** After splitting on a separator, each piece is re-checked — if still too large, the next separator down the list is tried on that piece.
**The bug:** The original version passed the *full* `_SEPARATORS` list on every recursive call. Each split re-attaches the separator to the end of a piece (e.g. `"para" + "\n\n"` → `"para\n\n"`) so paragraph breaks survive repacking. But re-attaching the separator means the *same* separator (`"\n\n"`) is still present in the recursed-on string — so the same branch matches again on the next call, splits into the same pieces, re-attaches again, forever. Infinite recursion / stack overflow on certain inputs.
**The fix:** Thread the *remaining* separator slice through recursive calls instead of always starting from the top:
```python
def _split_prose(text: str, target: int, _seps: list[str] | None = None) -> list[str]:
    if _seps is None:
        _seps = _SEPARATORS
    if count_tokens(text) <= target:
        return [text] if text.strip() else []
    for i, sep in enumerate(_seps):
        if sep == "":
            return [text]
        if sep not in text:
            continue
        raw_pieces = text.split(sep)
        atoms = []
        for j, piece in enumerate(raw_pieces):
            rejoined = (piece + sep) if j < len(raw_pieces) - 1 else piece
            atoms.extend(_split_prose(rejoined, target, _seps[i + 1:]))  # only what's left
        return atoms
    return [text]
```
**Lesson:** Whenever a recursive splitter re-attaches a delimiter to make the output "look right," the recursive step must not be allowed to re-match that same delimiter — pass a shrinking view of the separator list, not the full list, on every call.

---

## Greedy packing at the token-ID level, not the string level

**What:** `chunk_text` builds chunks by accumulating token IDs (`list[int]`) in a buffer (`cur_ids`), not by concatenating strings.
**Why:** Overlap has to be exact — "carry the last 50 tokens into the next chunk" is a token-ID slice operation. Doing this on decoded strings would require re-tokenizing and hoping character boundaries line up with token boundaries, which they don't in BPE.
**How:**
```python
if cur_ids and len(cur_ids) + len(atom_ids) > target_tokens:
    chunks.append(_ENC.decode(cur_ids))
    overlap_text = _ENC.decode(cur_ids[-overlap_tokens:])
    cur_ids = _ENC.encode(overlap_text + atom)   # re-encode as one unit
else:
    cur_ids.extend(atom_ids)
```
Note the overlap is decoded to text and *re-encoded* together with the new atom, rather than concatenating raw token ID lists directly (`overlap_ids + atom_ids`). This keeps BPE merges consistent across the junction — two token ID lists concatenated naively can represent different (usually more, sometimes fewer) tokens than encoding the equivalent joined string once.

---

## Why the overlap test checks substrings, not token IDs

**What:** The test suite validates overlap via `test_chunk_text_overlap_content_appears_in_previous_chunk`, which checks that the first ~50 characters of chunk N+1 appear somewhere in chunk N — not that `encode(chunk[i])[-50:] == encode(chunk[i+1])[:50]`.
**Why:** `chunk_text`'s return value is `.strip()`-ped before being returned. Stripping can shift where whitespace/token boundaries fall relative to the internal `cur_ids` buffer used during construction. So re-encoding the final (stripped) chunk strings and comparing token ID slices is unreliable — the *implementation's* internal token math is exact, but that exactness doesn't survive a round-trip through `decode → strip → encode` at the test boundary.
**Lesson:** Test the externally observable contract (semantic overlap is present) rather than reimplementing the internal invariant (exact token ID equality) when a lossy transformation (`.strip()`) sits between the two.

---

## Large code blocks: overflow without overlap

**What:** If a code-block atom alone exceeds `target_tokens`, it's flushed as its own standalone chunk — no overlap prefix from the previous chunk, no overlap suffix carried into the next.
**Why:** The spec explicitly allows code blocks to exceed the token target rather than being split (a split code block is worse than an oversized one). Applying overlap logic to something already over-budget would only make it larger for no benefit, since the whole point of overlap is stitching split *prose* context back together — a code block was never split.
**How:**
```python
if is_code and len(atom_ids) > target_tokens:
    if cur_ids:
        chunks.append(_ENC.decode(cur_ids))  # flush whatever prose was pending
        cur_ids = []
    chunks.append(atom)                       # emit as-is, no overlap
    continue
```

---

## Deterministic chunk IDs via truncated SHA-1

**What:** `chunk_id` is built as `f"stripe-{sha1(url)[:8]}-{chunk_index}"`.
**Why:** IDs need to be stable across re-runs (same doc → same chunk IDs, useful for idempotent upserts into a vector store later) and unique across the whole corpus. Hashing the URL avoids collisions between docs while keeping IDs short and filesystem/log-friendly compared to embedding a full URL.
**How:**
```python
url_hash = hashlib.sha1(url.encode()).hexdigest()[:8]
chunk_id = f"stripe-{url_hash}-{i}"
```
8 hex characters (32 bits) is far more than enough to avoid collisions across ~500 docs.

---

## `statistics` module for corpus-level reporting

**What:** `chunk_corpus` reports avg/min/median/max chunks-per-doc and token-count-per-chunk using `statistics.mean` / `statistics.median` rather than hand-rolled math.
**Why:** These are exactly the shape of "distribution sanity check" numbers a human wants after a batch job — median in particular is more informative than mean for catching a few pathological outlier docs without being skewed by them.
**How:** Same generator-driven, single-pass-over-the-file pattern as the loader ([[02-docs-loader]]) — `chunk_doc` is a generator, stats lists are built incrementally per doc, nothing is held in memory beyond one doc's chunks at a time.
