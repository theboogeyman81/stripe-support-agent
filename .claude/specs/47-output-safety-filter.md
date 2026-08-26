# Spec 47 — Output Safety Filter

## Feature
After the LLM generates an answer, the answer is scanned for toxic or unsafe
content before being returned to the user. If unsafe patterns are detected the
answer is replaced with a safe fallback message. The check is regex/keyword-based
— no additional API call. This is a defence-in-depth layer: Gemini already has
built-in safety filters, but this guardrail catches any edge cases that slip
through, and keeps the safety boundary entirely within our own code.

## Why
Even with Gemini's built-in filters, a support agent about payments could
theoretically produce: fraud instructions (bypass fraud detection, card skimming),
distressing self-harm content (a user venting financial despair), or profanity.
Blocking at our layer, before returning to the user, ensures no unsafe text ever
reaches the client regardless of the upstream LLM's behaviour.

## Input contract
- `text: str` — the LLM-generated answer, before any other output post-processing.

## Output contract
- `SafetyResult` dataclass:
  - `is_safe: bool` — `True` if no unsafe patterns were found.
  - `reason: str | None` — matched category label for logging (`"profanity"`,
    `"self_harm"`, `"fraud_instructions"`, `"threats"`). `None` if safe.

## Scope (in)
- `src/guardrails/safety.py` — `SafetyResult` dataclass + `UNSAFE_FALLBACK`
  constant + `check_safety(text: str) -> SafetyResult`, pattern-based.
- `src/api/routes/ask.py` — call `check_safety` immediately after `generate()`
  returns (before the grounding check); if `not result.is_safe`, replace
  `result["answer"]` with `UNSAFE_FALLBACK` and skip the grounding check.
- `tests/test_safety.py` — unit tests, no network.

## Scope (out)
- No ML toxicity classifier — regex/keyword only.
- No integration with `/chat` route for now (same reason as feature 46 — agent
  output is not directly accessible at route level).
- No Langfuse logging — plain `print` at WARNING level is sufficient.
- Not an exhaustive profanity list — covers the most severe cases only.

## Dependencies
- New: none — `re` and `dataclasses` stdlib only.
- Existing: `src/api/routes/ask.py`.

## Acceptance criteria
1. `uv run pytest tests/test_safety.py -v` — all tests pass.
2. Unit test: answer containing a strong profanity word → `is_safe=False,
   reason="profanity"`.
3. Unit test: answer containing "kill yourself" → `is_safe=False,
   reason="self_harm"`.
4. Unit test: normal Stripe answer → `is_safe=True, reason=None`.
5. Manual: send a normal Stripe question to `/ask`; verify the answer is not the
   fallback string.

## Failure modes to handle
- **Empty answer**: return `SafetyResult(is_safe=True, reason=None)` — empty
  strings cannot be unsafe (the grounding check will handle them).
- **Fallback strings as input**: if the grounding check's `UNGROUNDED_FALLBACK`
  were somehow passed, it must not trigger the safety filter — ensure patterns
  are specific enough not to match normal English phrases.
- **Case variants and spacing**: all patterns compiled with `re.IGNORECASE`.

## Notes

### Pattern categories and examples
| Category label | Sample patterns |
|---|---|
| `profanity` | 5–6 strong English profanity words/slurs (exact words, word boundaries) |
| `self_harm` | `r"kill\W+yourself"`, `r"self[\W_]harm"`, `r"suicide"`, `r"end\W+your\W+life"` |
| `fraud_instructions` | `r"steal\W+card"`, `r"card\W+skimming"`, `r"bypass\W+fraud"`, `r"launder\W+money"`, `r"carding\W+tutorial"` |
| `threats` | `r"i\W+will\W+kill"`, `r"bomb\W+threat"`, `r"death\W+threat"` |

Keep the profanity list intentionally short — this is a Stripe support agent;
elaborate toxic language is extremely unlikely to appear in LLM responses to
payment questions. The goal is catching egregious slips, not comprehensive
content moderation.

### `UNSAFE_FALLBACK` constant (exact, importable by tests)
`"I'm unable to provide that response. Please contact Stripe support directly."`

### Pipeline order in `ask.py` after this feature
```
generate() → result
  → check_safety(result["answer"])      [feature 47 — new, runs first]
      if unsafe: result["answer"] = UNSAFE_FALLBACK, skip grounding
  → check_grounding(result["answer"], chunks)   [feature 46]
      if ungrounded: result["answer"] = UNGROUNDED_FALLBACK
  → semantic_store (only if grounded)
  → return AskResponse
```
