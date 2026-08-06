# Spec 19 — Agent System Prompt

## Feature
Replace the placeholder two-sentence `SYSTEM_PROMPT` in `src/agent/agent.py`
with a structured prompt that explicitly instructs the agent when to use each
of its four tools (`search_docs`, `calculate`, `lookup_user`, `create_ticket`).
Without this guidance, the model picks tools inconsistently — it may answer a
billing complaint with docs text instead of opening a ticket, or ignore the
user's email instead of calling `lookup_user`. A well-designed prompt makes
tool selection reliable and predictable.

## Why
The phase-3 exit checklist requires the agent to reliably choose `search_docs`
for factual questions and `create_ticket` for account/billing complaints. The
four tools now exist; this feature teaches the agent to use them correctly.
Feature 20 (`multi-turn-state`) and feature 21 (`chat-endpoint`) build on the
assumption that the agent behaves consistently — that depends on this prompt.

## Input contract
- `src/agent/agent.py` — the only file that changes
- No new files, no new dependencies, no config changes

## Output contract

### `src/agent/agent.py` (modify)
Replace `SYSTEM_PROMPT` with a multi-section string. Required sections:

**Role** — one sentence establishing identity and purpose.

**Tool selection rules** — one rule per tool, written as explicit IF/THEN
instructions so the model has unambiguous decision criteria:

| Trigger | Tool to call |
|---------|-------------|
| User asks a factual question about Stripe products, APIs, or documentation | `search_docs` |
| User provides their email address or asks about their account, plan, or status | `lookup_user` |
| User reports a billing problem, account issue, or complaint that cannot be resolved from documentation | `create_ticket` |
| A fee, amount, or arithmetic calculation is needed | `calculate` |

**Behaviour rules** — a short list covering:
- Always call `lookup_user` before `create_ticket` when the user has provided
  an email, so the ticket can reference their account.
- If `search_docs` returns no relevant results, say so honestly rather than
  guessing.
- If `lookup_user` returns "No user found", relay that message and ask the
  user to verify their email.
- Keep answers concise — one to three sentences after tool results unless more
  detail is needed.

The prompt must be a single string assigned to `SYSTEM_PROMPT`. Use a
multiline string (`""" ... """`) or concatenated string — either is fine as
long as ruff passes. No other changes to `agent.py`.

## Scope (in)
- `src/agent/agent.py` — replace `SYSTEM_PROMPT` only
- `tests/test_agent.py` — update or add assertions that verify the prompt
  contains key guidance phrases

## Scope (out)
- No changes to tool implementations
- No changes to `run_agent()` or `create_agent()` logic
- No few-shot examples in the prompt (Phase 4+)
- No per-user or per-session dynamic prompt injection (Phase 4+)
- No changes to any API routes or config

## Dependencies
- New: none
- Existing: `src/agent/agent.py`, `tests/test_agent.py`

## Acceptance criteria
1. `uv run ruff check src/agent/agent.py` exits 0.
2. `uv run pytest tests/test_agent.py -v` passes.
3. `SYSTEM_PROMPT` contains the word `search_docs` (verifies tool name is
   explicit in the prompt):
   ```powershell
   uv run python -c "from src.agent.agent import SYSTEM_PROMPT; assert 'search_docs' in SYSTEM_PROMPT; print('OK')"
   ```
4. `SYSTEM_PROMPT` contains the word `create_ticket`:
   ```powershell
   uv run python -c "from src.agent.agent import SYSTEM_PROMPT; assert 'create_ticket' in SYSTEM_PROMPT; print('OK')"
   ```
5. `SYSTEM_PROMPT` contains the word `lookup_user`:
   ```powershell
   uv run python -c "from src.agent.agent import SYSTEM_PROMPT; assert 'lookup_user' in SYSTEM_PROMPT; print('OK')"
   ```
6. `SYSTEM_PROMPT` contains the word `calculate`:
   ```powershell
   uv run python -c "from src.agent.agent import SYSTEM_PROMPT; assert 'calculate' in SYSTEM_PROMPT; print('OK')"
   ```

## Failure modes to handle
- Prompt too vague → agent ignores tools: ensure each rule names the tool
  explicitly and describes a concrete trigger condition.
- Prompt too long → token cost increases: keep total prompt under 300 tokens.
  No lengthy preambles or repetition.

## Notes
- Naming tools explicitly in the system prompt (e.g. "call `search_docs`")
  is the most reliable approach with Gemini 2.5 Flash — it reduces ambiguity
  compared to describing what the tool does and expecting the model to infer
  the name.
- The tests for this feature assert on `SYSTEM_PROMPT` string content, not on
  live agent behaviour — live tool-selection testing requires API calls and
  belongs in the eval phase (Phase 5).
- Existing `test_agent.py` tests mock the model and do not make API calls —
  they should continue to pass unchanged. At most, add new assertions on the
  `SYSTEM_PROMPT` constant; do not rewrite existing tests.
