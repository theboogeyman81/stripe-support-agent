# Spec 46 — Output Hallucination Check

## Feature
After the LLM generates an answer, the answer is checked against the retrieved
chunks to verify it is grounded in the source material. Grounding is measured by
computing the overlap between content words in the answer and content words across
all retrieved chunks. If the overlap falls below a threshold the answer is replaced
with a safe fallback message — the user never sees a potentially hallucinated
response. No LLM call is made for the check; it is pure Python string processing.

## Why
Gemini can produce fluent, confident-sounding answers that have no basis in the
retrieved Stripe documentation. Returning these to users damages trust and may
spread misinformation about Stripe's APIs. Checking grounding against the actual
chunks used for generation is the cheapest safety net: it requires no extra API
call and catches the most egregious cases (answers about topics not in the chunks
at all).

## Input contract
- `answer: str` — the LLM-generated answer text.
- `chunks: list[dict]` — the retrieved chunks passed to `generate()`. Each chunk
  has at least a `"text"` field.

## Output contract
- `GroundingResult` dataclass:
  - `is_grounded: bool` — `True` if the answer is sufficiently grounded.
  - `overlap_score: float` — ratio of answer content words found in chunk content
    words; range `[0.0, 1.0]`.

## Scope (in)
- `src/guardrails/hallucination.py` — `GroundingResult` dataclass +
  `check_grounding(answer: str, chunks: list[dict]) -> GroundingResult`.
- `src/api/routes/ask.py` — call `check_grounding` after `generate()` returns;
  if `not result.is_grounded`, replace `result["answer"]` with the fallback string
  `"I couldn't find a reliable answer in Stripe's documentation for that question."`.
- `tests/test_hallucination.py` — unit tests, no network.

## Scope (out)
- No integration with `/chat` route — the agent pipeline does not expose
  `chunks` at the route level; a future feature can add it there.
- No LLM-as-judge — that is a separate eval feature (already in Phase 5).
- No Langfuse logging of grounding scores — plain `print` is sufficient for now.
- No tunable threshold via `Settings` — hardcode at `0.15` for this feature.

## Dependencies
- New: none — stdlib only (`re`, `dataclasses`).
- Existing: `src/api/routes/ask.py`.

## Acceptance criteria
1. `uv run pytest tests/test_hallucination.py -v` — all tests pass.
2. Unit test with answer words fully contained in chunk text → `is_grounded=True`,
   `overlap_score >= 0.15`.
3. Unit test with answer containing words unrelated to any chunk → `is_grounded=False`,
   `overlap_score < 0.15`.
4. Manual: send a normal Stripe question to `/ask`; verify response returns an
   answer (not the fallback) and `answer` field is non-empty.

## Failure modes to handle
- **Empty answer**: treat as ungrounded → `is_grounded=False`, `overlap_score=0.0`.
- **Empty chunks list**: treat as ungrounded (no source to ground against).
- **Answer is the fallback string itself**: do not re-check; the replacement happens
  after the check, not recursively.
- **Very short answers** (e.g. "Yes." or "No."): content words may be empty after
  filtering — treat as grounded (do not penalise short affirmatives).

## Notes

### Algorithm
```
STOPWORDS = {"the", "a", "an", "is", "it", "in", "of", "to", "and", "or",
             "for", "on", "at", "by", "be", "are", "was", "were", "that",
             "this", "with", "as", "from", "not", "but", "have", "has", "do",
             "i", "you", "we", "they", "he", "she", "how", "what", "which"}

def _content_words(text: str) -> set[str]:
    tokens = re.findall(r"[a-z]{3,}", text.lower())   # ≥3-char alpha only
    return {t for t in tokens if t not in STOPWORDS}

chunk_words  = union of _content_words(chunk["text"]) for all chunks
answer_words = _content_words(answer)

if not answer_words:                     # short answer edge case
    return GroundingResult(True, 1.0)
overlap_score = len(answer_words & chunk_words) / len(answer_words)
is_grounded   = overlap_score >= 0.15
```

### Why 0.15 threshold
LLMs rephrase heavily — a grounded answer about "PaymentIntent creation" might
use words like "creates", "initialise", "flow" that don't appear verbatim in the
chunk. 0.15 catches only severe mismatches (fewer than 1 in 7 content words
overlap) while tolerating paraphrasing. This is deliberately conservative — false
negatives (ungrounded answers passing) are better than false positives (correct
answers blocked).

### Fallback string (exact)
`"I couldn't find a reliable answer in Stripe's documentation for that question."`

This string is a constant in `hallucination.py` so tests can import and assert
against it without hardcoding it twice.
