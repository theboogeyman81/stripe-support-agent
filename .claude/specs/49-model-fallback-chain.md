# Spec 49 — Model Fallback Chain

## Feature
Wrap the Gemini call in `src/rag/generator.py` with a fallback chain so that a
single upstream failure does not surface as a 502 to the user. The chain has
three levels:

1. **Primary** — current Gemini 2.5 Flash call (unchanged behaviour).
2. **Secondary** — retry with a lighter Gemini model (`gemini-2.0-flash`) on
   `google.genai` exceptions. Same prompt, same caching logic.
3. **Apology** — if both models fail, return a canned apology response dict
   instead of raising, so the `/ask` route can return a graceful answer rather
   than a 502.

The fallback is transparent to the caller: `generate()` always returns the same
dict shape `{answer, input_tokens, output_tokens, cost_usd, cache_hit}`.

## Why
Currently any Gemini API error propagates as a raw exception, caught in `ask.py`
as a 502. For transient outages or rate-limit bursts, a lighter model or a polite
apology is far better UX than an error page. This also sets up feature 50
(circuit-breaker) which will track the failure count that decides when to skip
the primary model entirely.

## Input contract
`generate()` in `src/rag/generator.py` — same signature as today:
```python
def generate(
    question: str,
    chunks: list[dict],
    redis_client: redis_lib.Redis | None = None,
    cache_ttl: int = 3600,
) -> dict:
```

## Output contract
Same dict as today: `{answer, input_tokens, output_tokens, cost_usd, cache_hit}`.

Additional field on apology path:
- `"fallback_level": int` — `0` = primary succeeded, `1` = secondary used,
  `2` = apology returned. Callers may ignore this field; it is for logging.

## Scope (in)
- `src/rag/generator.py` — extract a `_call_model(model: str, prompt: str, ...) -> dict`
  helper that performs a single Gemini call + cost calculation. Wrap `generate()`
  with a try/except that attempts primary, then secondary, then returns apology.
- `src/rag/generator.py` — define constants:
  - `GEMINI_MODEL_PRIMARY = "gemini-2.5-flash"` (rename from `GEMINI_MODEL`)
  - `GEMINI_MODEL_SECONDARY = "gemini-2.0-flash"`
  - `APOLOGY_ANSWER = "I'm sorry, I'm temporarily unable to answer. Please try again shortly or contact Stripe support."`
- `tests/test_generator_fallback.py` — unit tests mocking `genai.Client`.
  Existing `tests/test_generator.py` must continue to pass unchanged.

## Scope (out)
- No change to the `/ask` route — `generate()` no longer raises on Gemini errors,
  so the `try/except HTTPException` in `ask.py` needs no modification.
- No circuit-breaker logic here — that is feature 50. Feature 49 is purely the
  fallback chain inside `generate()`.
- No Langfuse tracing changes.
- No new dependencies — `google-genai` already installed.

## Dependencies
- New: none.
- Existing: `src/rag/generator.py`, `src/config.py`.

## Acceptance criteria
1. `uv run pytest tests/test_generator_fallback.py -v` — all tests pass.
2. `uv run pytest tests/test_generator.py -v` — existing tests still pass.
3. Unit test: primary raises → secondary called → secondary answer returned,
   `fallback_level=1`.
4. Unit test: primary raises, secondary raises → apology answer returned,
   `fallback_level=2`.
5. Unit test: primary succeeds → secondary never called, `fallback_level=0`.
6. `uv run ruff check src/rag/generator.py tests/test_generator_fallback.py` passes.

## Failure modes to handle
- **Primary raises any exception from `google.genai`**: catch, log `[WARNING]`,
  attempt secondary.
- **Secondary raises any exception**: catch, log `[WARNING]`, return apology dict.
- **Apology path**: `input_tokens=0, output_tokens=0, cost_usd=0.0, cache_hit=False,
  fallback_level=2`. The apology answer is never cached.

## Notes

### `_call_model` helper signature
```python
def _call_model(model: str, prompt: str, settings: Settings) -> dict:
    """Call a single Gemini model and return result dict (no caching)."""
```
Returns `{answer, input_tokens, output_tokens, cost_usd}` — no `cache_hit` or
`fallback_level` (those are added by `generate()`).

### Updated `generate()` skeleton
```python
def generate(question, chunks, redis_client=None, cache_ttl=3600) -> dict:
    prompt = build_prompt(question, chunks)
    settings = Settings()

    # Exact-match cache lookup (unchanged)
    ...

    # Fallback chain
    for level, model in enumerate([GEMINI_MODEL_PRIMARY, GEMINI_MODEL_SECONDARY]):
        try:
            result = _call_model(model, prompt, settings)
            result["cache_hit"] = False
            result["fallback_level"] = level
            # Cache write (only for level 0 or 1, never apology)
            ...
            return result
        except Exception as exc:
            print(f"[WARNING] Gemini model {model} failed: {exc}")

    # Apology
    return {
        "answer": APOLOGY_ANSWER,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "cache_hit": False,
        "fallback_level": 2,
    }
```

### Why not separate the apology into a guardrail?
The guardrails in `src/guardrails/` operate on the *output* of `generate()`. If
`generate()` raises, the route's `try/except` catches it before any guardrail
runs. Keeping the apology inside `generate()` means the guardrails always receive
a valid string, no special-casing needed in the route.
