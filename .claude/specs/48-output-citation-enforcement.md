# Spec 48 — Output Citation Enforcement

## Feature
After the LLM generates an answer, verify that the answer actually references
content from the retrieved chunks before returning it. Specifically: if the
retrieved chunk list is non-empty but the generated answer shares zero content
words with any chunk, it is treated as uncited and replaced with the ungrounded
fallback. This is a stricter companion to the hallucination grounding check
(feature 46) — where feature 46 uses a soft overlap threshold (0.15), this
feature adds a hard zero-citation gate: if `sources` would be empty (no chunks
survived deduplication) but the answer is non-trivial, reject it.

In practice the enforcement rule is: **if `sources` is empty after deduplication
and the answer is non-empty and non-trivial (has content words), replace the
answer with `UNGROUNDED_FALLBACK`**. This catches the edge case where `retrieve()`
returns chunks that are all missing `doc_url`, producing an empty sources list
while still sending the answer through.

## Why
The `/ask` endpoint always returns a `sources` list alongside the answer. If that
list is empty, the user has no way to verify the answer — it is effectively
uncited. Blocking uncited answers closes a gap between feature 46 (soft grounding)
and the real user-facing contract: every answer comes with at least one source.

## Input contract
- `answer: str` — the (possibly already safety/grounding-filtered) answer string.
- `sources: list[SourceItem]` — the deduplicated source list built from chunks.

## Output contract
- `bool` — `True` if the answer is citation-enforced (sources non-empty OR answer
  is trivial), `False` if the answer must be replaced.
- If `False`: caller replaces `result["answer"]` with `UNGROUNDED_FALLBACK` from
  `src/guardrails/hallucination.py` (reuse existing constant, do not define a new
  one).

## Scope (in)
- `src/guardrails/citation.py` — `enforce_citation(answer: str, sources: list) -> bool`.
  Pure function, no dataclass needed (simple bool return).
- `src/api/routes/ask.py` — call `enforce_citation` after sources are built and
  after the grounding check; if it returns `False`, replace answer with
  `UNGROUNDED_FALLBACK` and set `cache_answer = False`.
- `tests/test_citation.py` — unit tests, no network.

## Scope (out)
- No change to `/chat` route — the agent route does not expose a sources list.
- No new fallback string — reuse `UNGROUNDED_FALLBACK` from hallucination module.
- No LLM-based citation check — purely structural (sources list length).

## Dependencies
- New: none — stdlib only.
- Existing: `UNGROUNDED_FALLBACK` from `src/guardrails/hallucination.py`,
  `src/api/routes/ask.py`.

## Acceptance criteria
1. `uv run pytest tests/test_citation.py -v` — all tests pass.
2. Unit test: non-empty answer + empty sources list → `enforce_citation` returns
   `False`.
3. Unit test: non-empty answer + non-empty sources list → returns `True`.
4. Unit test: empty answer + empty sources list → returns `True` (trivial, let
   grounding handle).
5. `uv run ruff check src/guardrails/citation.py src/api/routes/ask.py tests/test_citation.py` passes.

## Failure modes to handle
- **Empty answer**: return `True` — trivial answers pass through; grounding check
  already handled empty strings.
- **Answer of only stopwords/short words** (no content words): return `True` —
  same as empty, not worth blocking.
- **Sources non-empty**: always return `True` regardless of answer content —
  citation is structural, not semantic.

## Notes
### `enforce_citation` algorithm
1. If `sources` is non-empty → return `True`.
2. If `answer` has no content words (use same `_content_words` logic as feature 46,
   or inline the same 3-char alpha filter) → return `True`.
3. Otherwise (sources empty + answer has content words) → return `False`.

### Pipeline order in `ask.py` after this feature
```
generate() → result
  → check_safety()           [feature 47]
  → check_grounding()        [feature 46]
  → build sources list       [existing]
  → enforce_citation()       [feature 48 — new]
      if False: answer = UNGROUNDED_FALLBACK, cache_answer = False
  → semantic_store (gated on cache_answer)
  → return AskResponse
```

### Why not extend the grounding check?
Feature 46 already handles the semantics (overlap score). This check handles
the structural contract: every non-trivial answer must have at least one
verifiable source. Keeping them separate makes each guardrail single-purpose
and independently testable.
