# Spec 43 — Input PII Redaction

## Feature
Before any user query reaches the LLM, Langfuse trace, or Redis cache, it is
scanned for personally identifiable information and redacted in-place. Detected
PII is replaced with typed placeholders (`[EMAIL]`, `[PHONE]`, `[CARD]`,
`[SSN]`). The original text is never logged, stored in cache, or sent upstream.

## Why
Stripe handles sensitive financial data. Users may paste card numbers, emails,
or phone numbers into support queries. Letting raw PII flow into LLM prompts
(where it may be logged by the provider), Langfuse traces, or Redis keys is a
compliance and privacy risk. Redaction at the earliest pipeline stage — before
anything else touches the text — is the safest approach.

## Input contract
- `text: str` — raw user query string.

## Output contract
- `RedactionResult` dataclass:
  - `redacted_text: str` — query with PII replaced by placeholders.
  - `replacements: list[dict]` — each entry: `{"type": str, "original": str, "placeholder": str}`.
  - `pii_detected: bool` — `True` if any PII was found.

## Scope (in)
- `src/guardrails/__init__.py` — empty package init.
- `src/guardrails/pii_redaction.py` — `redact_pii(text: str) -> RedactionResult`, regex-based.
- Integration in `src/api/routes/ask.py` (or equivalent agent entry point) — redact before retrieval.
- `tests/test_pii_redaction.py` — unit tests, no network.

## Scope (out)
- No ML-based NER (regex only for now).
- No redaction of names, addresses, or dates — out of scope until a later feature.
- No reversible redaction (no de-anonymisation needed here).
- No changes to Langfuse tracing internals — the redacted text is what reaches
  the tracer, no extra Langfuse work required.

## Dependencies
- New: none — `re` is stdlib.
- Existing: `src/api/routes/ask.py`, `src/config.py`.

## Acceptance criteria
1. `uv run pytest tests/test_pii_redaction.py -v` — all tests pass.
2. `curl -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"My card is 4242 4242 4242 4242 and email is foo@bar.com\"}" | python -m json.dumps` — response answer does not contain `4242` or `foo@bar.com`.
3. `curl -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"How do I create a PaymentIntent?\"}" | python -m json.dumps` — clean query is unchanged, `pii_detected` is false in logs.

## Failure modes to handle
- **Regex false-positive on non-PII numbers** (e.g. Stripe test key `sk_test_...`): card regex must require 13–19 consecutive digits with optional spaces/dashes, not match arbitrary long strings.
- **Multiple PII types in one query**: all must be redacted; replacements list must contain one entry per match.
- **Empty string input**: return `RedactionResult(redacted_text="", replacements=[], pii_detected=False)` without error.

## Notes
- Regex patterns to cover:
  - **Email**: `[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}`
  - **Phone**: E.164 and common US formats — `(\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}`
  - **Card (Luhn-pattern)**: `\b(?:\d[ \-]?){13,18}\d\b` — 13–19 digit sequences with optional separators; post-filter with a Luhn check to cut false positives.
  - **SSN**: `\b\d{3}[- ]?\d{2}[- ]?\d{4}\b`
- Luhn check is pure Python, no library needed — implement inline.
- Order of redaction: card → SSN → phone → email (most-to-least specific, avoids partial overlaps).
- The `replacements` list is for observability only (logged at DEBUG level); it is never returned in the API response.
