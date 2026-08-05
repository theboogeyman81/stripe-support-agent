# Spec 14 — Agent Scaffold

## Feature
Create the `src/agent/` module and wire up a Pydantic AI agent bound to
Gemini 2.5 Flash. The agent is callable with a plain question and returns a
text answer plus token usage. No tools, no conversation history, no chat
endpoint — those come in features 15–21. This feature is the foundation every
subsequent Phase 3 feature builds on.

## Why
The Phase 1/2 pipeline is a fixed retrieve-then-generate chain. An agent
framework lets the model decide which tool to call (or not call), handle tool
errors, and loop until it has a complete answer. Pydantic AI is the approved
framework. This scaffold proves the agent initialises, connects to Gemini, and
produces a structured result before we add complexity.

## Input contract
- `src/config.py` — `Settings.gemini_api_key` (already present)
- No new environment variables required

## Output contract

### `src/agent/__init__.py`
Empty init — makes `src.agent` a package.

### `src/agent/agent.py`
Two public functions:

```python
def create_agent(settings: Settings) -> Agent:
    """Return a configured Pydantic AI Agent bound to Gemini 2.5 Flash."""

def run_agent(question: str, settings: Settings) -> dict:
    """Run the agent on a question and return result dict.

    Returns:
        {
            "answer": str,
            "input_tokens": int,
            "output_tokens": int,
            "cost_usd": float,
        }
    """
```

`create_agent` must not connect to any external service at call time — it only
configures the agent object. `run_agent` calls `create_agent` internally and
executes the agent synchronously (Pydantic AI's `run_sync`).

Cost calculation uses the same rates as `src/rag/generator.py`:
- Input: $0.30 / 1M tokens
- Output: $2.50 / 1M tokens

## Scope (in)
- `src/agent/__init__.py` — new, empty
- `src/agent/agent.py` — new, two public functions above
- `tests/test_agent.py` — new test file
- A minimal system prompt string defined as a module-level constant in
  `agent.py` so the agent has a role identity (e.g. "You are a Stripe support
  assistant."). Keep it to 1–2 sentences; full prompt design is feature 19.

## Scope (out)
- No tools attached to the agent (features 15–18)
- No system prompt tuning (feature 19)
- No conversation history (feature 20)
- No `/chat` endpoint (feature 21)
- No changes to the existing `/ask` endpoint — it stays on the Phase 1/2
  retrieve-then-generate pipeline until feature 21 replaces it
- No async — use Pydantic AI's `run_sync` throughout

## Dependencies
- New: `pydantic-ai[gemini]` — **must be approved before adding to pyproject.toml**
- Existing: `google-genai` (already installed), `src/config.py`

## Acceptance criteria
1. `uv run python -c "from src.agent.agent import create_agent, run_agent; print('OK')"` exits 0.
2. `uv run pytest tests/test_agent.py -v` passes (all external calls mocked).
3. `uv run ruff check src/agent/agent.py` exits 0.
4. Running `uv run python -c "from src.config import Settings; from src.agent.agent import run_agent; r = run_agent('What is a PaymentIntent?', Settings()); print(r['answer'][:80])"` against the live API returns a non-empty string. (Costs < $0.001 — confirm before running.)

## Failure modes to handle
- `gemini_api_key` missing or invalid: let the exception propagate — `Settings`
  validation already catches missing keys at startup.
- Empty question passed to `run_agent`: raise `ValueError("question must not be empty")` before calling the agent, mirroring the existing `generator.py` guard.

## Notes
- Pydantic AI's `GeminiModel` requires either the `GEMINI_API_KEY` env var or
  an explicit `api_key` kwarg. Pass it explicitly from `Settings` so the agent
  is testable without env vars.
- `pydantic-ai[gemini]` is the package name; the extra installs the Gemini
  provider. Confirm the exact extra name against PyPI before adding — it may
  be `pydantic-ai-slim[gemini]` depending on the release.
- The model string to use is `"gemini-2.5-flash"` — same as `generator.py`.
- Token counts come from Pydantic AI's `RunResult.usage()`. The exact field
  names (`request_tokens`, `response_tokens`) differ from google-genai's
  `usage_metadata` — verify against Pydantic AI docs during planning.
