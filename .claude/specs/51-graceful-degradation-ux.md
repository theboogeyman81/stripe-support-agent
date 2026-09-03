# Spec 51 — Graceful Degradation UX

## Feature
Expose degradation state in the `AskResponse` so API consumers can tell when
they received a fallback answer rather than a real one. Currently when guardrails
fire (unsafe, ungrounded, uncited) or the fallback chain activates (secondary
model, apology), the response body is identical in shape to a healthy answer —
the caller has no way to detect that quality dropped. This feature adds three
fields to `AskResponse`: `degraded` (bool), `degradation_reason` (str | None),
and `fallback_level` (int). When both Gemini models fail and the apology is
returned, a `Retry-After: 60` header is also sent so callers know how long to
back off.

## Why
A client that can't distinguish a real answer from an apology will surface
low-quality content without warning. Exposing the degradation signal lets the
caller dim the response, show a "try again" prompt, or log a UX metric. It also
makes integration tests trivial — assert `degraded=False` in the happy path,
`degraded=True` in the broken path.

## Input contract
- `src/api/routes/ask.py` — the existing ask route, which already computes
  safety, grounding, citation, and `fallback_level` internally.
- `src/api/schemas.py` — the existing `AskResponse` schema.

## Output contract
Updated `AskResponse`:
```json
{
  "answer": "...",
  "sources": [...],
  "input_tokens": 100,
  "output_tokens": 20,
  "cost_usd": 0.00008,
  "cache_hit": false,
  "degraded": false,
  "degradation_reason": null,
  "fallback_level": 0
}
```

Field rules:
- `degraded: bool` — `True` whenever any guardrail replaces the answer OR
  `fallback_level >= 1`. Default `False`.
- `degradation_reason: str | None` — first degradation cause; `None` when
  `degraded=False`. Possible values:
  - `"unsafe_output"` — safety filter fired
  - `"ungrounded"` — hallucination check fired
  - `"uncited"` — citation enforcement fired
  - `"model_fallback"` — secondary model was used (`fallback_level == 1`)
  - `"service_unavailable"` — apology returned (`fallback_level == 2`)
- `fallback_level: int` — directly from `result["fallback_level"]`; 0 = primary,
  1 = secondary, 2 = apology. Default `0`.

HTTP header added only when `fallback_level == 2`:
```
Retry-After: 60
```

Semantic cache hits (`cache_hit=True`) early-return before guardrails run;
they always return `degraded=False, degradation_reason=None, fallback_level=0`
(they represent a clean prior answer).

## Scope (in)
- `src/api/schemas.py` — add three fields to `AskResponse`.
- `src/api/routes/ask.py` — track `degraded` + `degradation_reason` through
  the safety/grounding/citation block; pass `fallback_level`; use
  `fastapi.Response` to add `Retry-After` header when `fallback_level == 2`.
- `tests/test_ask_degradation.py` — unit tests for the new fields using the
  FastAPI test client, all upstream dependencies mocked.

## Scope (out)
- No changes to the `/chat` route — it uses the agent pipeline, not the
  guardrail stack.
- No changes to Langfuse tracing (a future feature can log degradation events).
- No client-side UI changes (this is an API-only project).
- No changes to the `Retry-After` value — it matches `COOLDOWN_SECONDS = 60`
  from the circuit breaker and is hardcoded in the route.

## Dependencies
- New: none.
- Existing: `fastapi.Response` (already available in FastAPI); `src/api/schemas.py`;
  `src/api/routes/ask.py`.

## Acceptance criteria
1. `uv run pytest tests/test_ask_degradation.py -v` — all tests pass.
2. `uv run ruff check src/api/schemas.py src/api/routes/ask.py tests/test_ask_degradation.py` passes.
3. Happy-path request returns `degraded=false, degradation_reason=null, fallback_level=0`.
4. When safety filter fires, response has `degraded=true, degradation_reason="unsafe_output"`.
5. When grounding check fires, response has `degraded=true, degradation_reason="ungrounded"`.
6. When citation enforcement fires, response has `degraded=true, degradation_reason="uncited"`.
7. When secondary model is used (`fallback_level=1`), response has
   `degraded=true, degradation_reason="model_fallback"`.
8. When apology is returned (`fallback_level=2`), response has
   `degraded=true, degradation_reason="service_unavailable"` and a
   `Retry-After: 60` header.
9. `uv run pytest tests/ -v` — all existing tests still pass.

## Failure modes to handle
- **result missing `fallback_level`** (e.g. exact-match cache hit returns early):
  default to `0` via `result.get("fallback_level", 0)`.
- **Multiple guardrails fire** (unsafe AND fallback_level=1): `degradation_reason`
  is the first cause in evaluation order: unsafe → ungrounded → uncited →
  model_fallback → service_unavailable. First match wins.

## Notes
- `degradation_reason` priority order matches the order guardrails are evaluated
  in `ask.py`: safety first, then grounding, then citation, then fallback level.
- The `Retry-After` header value (60) is intentionally hardcoded — it matches
  `COOLDOWN_SECONDS` but we don't import the constant from `circuit_breaker.py`
  to keep the route decoupled from the implementation detail.
- `fastapi.Response` is injected as a parameter to the route function
  (`response: Response`) — FastAPI's standard pattern for mutating headers without
  returning a `JSONResponse` directly.
