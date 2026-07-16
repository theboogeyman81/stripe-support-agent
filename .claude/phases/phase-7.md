# Phase 7 — Guardrails + fallback chains

> Draft.

## Goal
Inputs are sanitised, outputs are validated, failures degrade gracefully.

## Features (planned)
43. `input-pii-redaction` — strip cards, emails, phone numbers before LLM
44. `input-prompt-injection` — detect and reject known attack patterns
45. `input-off-topic` — classifier rejects clearly non-Stripe queries
46. `output-hallucination-check` — verify answer is grounded in retrieved chunks
47. `output-safety-filter` — block toxic or unsafe output
48. `output-citation-enforcement` — reject answers without cited chunks
49. `model-fallback-chain` — primary → secondary → cached → apology
50. `circuit-breaker` — open circuit on repeated failures, cool down
51. `graceful-degradation-ux` — user-visible messaging when degraded

## What you'll learn
- Guardrails as compositional layers, not a single library call
- When to reject vs sanitise vs warn
- Fallback chain design and the "silent quality drop" trap
- Circuit breaker patterns for AI APIs

## Exit checklist
- [ ] PII in input never appears in traces
- [ ] Prompt injection attempts return a safe refusal
- [ ] Ungrounded answers are blocked, user sees an "I don't know" response
- [ ] Simulated Gemini outage triggers fallback, user still gets an answer
- [ ] `LEARNINGS.md` updated with Phase 7 notes