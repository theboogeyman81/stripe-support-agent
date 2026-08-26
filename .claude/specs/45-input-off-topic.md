# Spec 45 — Input Off-Topic Classification

## Feature
After PII redaction and prompt injection detection, user queries are checked to
see if they are clearly unrelated to Stripe or payments. If a query matches no
Stripe-domain terms AND matches known off-topic domain patterns, the request is
rejected with a user-friendly 400 response before reaching retrieval or the LLM.
Ambiguous queries are always allowed through (fail open — over-blocking is worse
than under-blocking for a support agent).

## Why
Sending clearly off-topic queries (cooking tips, sports scores, weather) to the
retrieval pipeline wastes embedding compute and Gemini tokens, and produces
hallucinated non-answers that erode user trust. Blocking them at the guardrail
layer keeps cost down and response quality high. The "clearly" qualifier is
important: the classifier must not block legitimate edge-case Stripe questions.

## Input contract
- `text: str` — user query, already PII-redacted and injection-checked.

## Output contract
- `OffTopicResult` dataclass:
  - `is_off_topic: bool` — `True` only when the query is both non-Stripe AND
    matches an off-topic domain.
  - `reason: str | None` — matched off-topic domain name for logging (`"cooking"`,
    `"sports"`, etc.). `None` if not off-topic.

## Scope (in)
- `src/guardrails/off_topic.py` — `OffTopicResult` dataclass +
  `classify_topic(text: str) -> OffTopicResult`, keyword-based.
- `src/api/routes/ask.py` — after injection check, call classifier; raise
  `HTTPException(status_code=400, detail="This question doesn't appear to be about Stripe or payments. Please ask about Stripe products, APIs, or billing.")` if `is_off_topic`.
- `src/api/routes/chat.py` — same guard, same error response.
- `tests/test_off_topic.py` — unit tests, no network.

## Scope (out)
- No LLM-based classification — keyword/regex only, zero API cost.
- No per-user history or context — each query is classified in isolation.
- No logging to Langfuse — plain `print` at WARNING level is sufficient.
- No config-driven keyword lists — hardcoded is fine for this phase.

## Dependencies
- New: none — `re` stdlib only.
- Existing: `src/api/routes/ask.py`, `src/api/routes/chat.py`.

## Acceptance criteria
1. `uv run pytest tests/test_off_topic.py -v` — all tests pass.
2. `curl -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"What is the best recipe for chocolate cake?\"}" | python -c "import sys,json; d=json.load(sys.stdin); print(d)"` — response is HTTP 400 with detail mentioning Stripe.
3. `curl -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"How do I handle a failed payment?\"}" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('answer','')[:80])"` — answer returned normally (not blocked).
4. `curl -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"What is a webhook?\"}" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('answer','')[:80])"` — ambiguous-but-legitimate query is NOT blocked.

## Failure modes to handle
- **Legitimate Stripe questions with no explicit "Stripe" keyword** (e.g. "What is
  a webhook?", "How do I handle 402 errors?"): must not be blocked — the Stripe
  allowlist includes broad payment/API terms, not just the word "Stripe".
- **Off-topic query that incidentally contains a payment word** (e.g. "What is the
  price of a Big Mac?"): "price" alone should not qualify as a Stripe term — the
  allowlist must use specific payment-domain vocabulary.
- **Empty string**: return `OffTopicResult(is_off_topic=False, reason=None)` without error.
- **Very short queries** (1–2 words like "help" or "hello"): treat as ambiguous,
  allow through — do not block on vagueness alone.

## Notes

### Two-gate logic (both gates must pass to reject)
A query is off-topic only when:
1. **No Stripe/payment term matched** from the allowlist (case-insensitive, whole
   word where practical).
2. **An off-topic domain pattern matched** from the blocklist.

If either gate fails to fire, the query is allowed through.

### Stripe allowlist terms (examples — not exhaustive)
`stripe`, `payment`, `paymentintent`, `charge`, `refund`, `invoice`, `subscription`,
`webhook`, `checkout`, `connect`, `radar`, `billing`, `payout`, `dispute`,
`card`, `bank`, `transfer`, `customer`, `product`, `price`, `coupon`, `promo`,
`api`, `sdk`, `dashboard`, `account`, `merchant`, `fraud`, `3ds`,
`authentication`, `mandate`, `tax`, `issuing`, `terminal`, `identity`

### Off-topic domain blocklist (examples — not exhaustive)
| Domain label | Sample terms |
|---|---|
| `cooking` | recipe, ingredient, bake, cook, cuisine, dish, meal, oven |
| `sports` | football, basketball, soccer, nfl, nba, score, touchdown, match |
| `weather` | weather, forecast, temperature, humidity, rain, snow, sunny |
| `entertainment` | movie, film, actor, singer, song, album, celebrity, lyrics |
| `health` | symptom, diagnosis, medicine, doctor, hospital, prescription |

Use compiled `re.IGNORECASE` word-boundary patterns for each domain group.

### Implementation sketch
```python
_STRIPE_TERMS = re.compile(r"\b(stripe|payment|charge|refund|...)\b", re.IGNORECASE)
_DOMAINS = {
    "cooking": re.compile(r"\b(recipe|ingredient|bake|...)\b", re.IGNORECASE),
    ...
}

def classify_topic(text: str) -> OffTopicResult:
    if not text or not text.strip():
        return OffTopicResult(False, None)
    if _STRIPE_TERMS.search(text):          # gate 1: has Stripe term → pass
        return OffTopicResult(False, None)
    for domain, pattern in _DOMAINS.items():  # gate 2: matches off-topic domain?
        if pattern.search(text):
            return OffTopicResult(True, domain)
    return OffTopicResult(False, None)       # ambiguous → pass
```
