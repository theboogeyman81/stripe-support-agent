# Plan — Feature 14: Agent Scaffold

## Context

Phase 1/2 uses a fixed retrieve-then-generate pipeline. Phase 3 replaces the
generation step with a Pydantic AI agent so the model can eventually decide
which tools to call, loop, and reason. This feature wires up the bare agent
(no tools yet) and proves it connects to Gemini 2.5 Flash and returns a
structured result. Every subsequent Phase 3 feature adds tools or config on top
of this scaffold.

---

## Files to create or modify

| File | Action | Purpose |
|------|---------|---------|
| `src/agent/__init__.py` | **Create** | Makes `src.agent` a package (empty) |
| `src/agent/agent.py` | **Create** | `create_agent` + `run_agent` public functions |
| `tests/test_agent.py` | **Create** | Tests; all external calls mocked via TestModel |
| `pyproject.toml` | **Modify** | Add `pydantic-ai` to dependencies |

---

## Algorithm walkthrough

### Verified API (pydantic-ai 2.21.0)

Confirmed via live inspection in this session:

```python
# Correct construction — passes explicit API key without touching env vars
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai import Agent

model = GoogleModel("gemini-2.5-flash", provider=GoogleProvider(api_key=key))
agent = Agent(model, system_prompt=SYSTEM_PROMPT)

# Correct execution
result = agent.run_sync(question)
answer = result.output                  # str
usage  = result.usage                   # RunUsage property (NOT callable)
input_tokens  = usage.input_tokens      # int | None
output_tokens = usage.output_tokens     # int | None

# Correct test override
with agent.override(model=TestModel()):
    result = agent.run_sync("hello")    # no network call
```

Key gotchas confirmed:
- `Agent("google:gemini-2.5-flash")` (string shorthand) hits `GOOGLE_API_KEY` at construction — do NOT use this form; use `GoogleModel` + `GoogleProvider` instead.
- `result.usage` is a property, not a method — `result.usage()` raises `TypeError`.
- Field names are `input_tokens` / `output_tokens` (not `request_tokens` / `response_tokens`).
- `input_tokens` / `output_tokens` may be `None` with `TestModel` — guard with `or 0`.

### `src/agent/agent.py`

```python
from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from src.config import Settings

GEMINI_MODEL = "gemini-2.5-flash"
INPUT_PRICE_PER_M = 0.30   # USD per 1M input tokens
OUTPUT_PRICE_PER_M = 2.50  # USD per 1M output tokens

SYSTEM_PROMPT = (
    "You are a Stripe support assistant. "
    "Answer questions about Stripe products and APIs accurately and concisely."
)


def create_agent(settings: Settings) -> Agent:
    """Return a configured Pydantic AI Agent bound to Gemini 2.5 Flash."""
    model = GoogleModel(
        GEMINI_MODEL,
        provider=GoogleProvider(api_key=settings.gemini_api_key),
    )
    return Agent(model, system_prompt=SYSTEM_PROMPT)


def run_agent(question: str, settings: Settings) -> dict:
    """Run the agent on a question and return answer, token counts, and cost."""
    if not question.strip():
        raise ValueError("question must not be empty")
    agent = create_agent(settings)
    result = agent.run_sync(question)
    usage = result.usage
    input_tokens = usage.input_tokens or 0
    output_tokens = usage.output_tokens or 0
    cost_usd = (
        (input_tokens / 1_000_000) * INPUT_PRICE_PER_M
        + (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_M
    )
    return {
        "answer": result.output,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }
```

### `pyproject.toml`

Add `"pydantic-ai"` to the `dependencies` list (no extra needed — Gemini
support is built in, confirmed on 2.21.0).

---

## Test design (`tests/test_agent.py`)

All tests patch `src.agent.agent.create_agent` to return `Agent("test")` —
Pydantic AI's built-in no-network test model, so no real API calls are made.

```python
import pytest
from unittest.mock import patch
from pydantic_ai import Agent
from src.agent.agent import create_agent, run_agent
from src.config import Settings

def _settings() -> Settings:
    return Settings(
        gemini_api_key="test-key",
        voyage_api_key="test-key",
        qdrant_url="http://localhost:6333",
    )

def _test_agent() -> Agent:
    return Agent("test", system_prompt="test")
```

| Test | What it verifies |
|------|-----------------|
| `test_create_agent_returns_agent_instance` | `create_agent(settings)` returns a `pydantic_ai.Agent` — no network; GoogleProvider just stores the key at construction |
| `test_run_agent_returns_all_keys` | Result dict has exactly `answer`, `input_tokens`, `output_tokens`, `cost_usd` |
| `test_run_agent_answer_is_string` | `result["answer"]` is a `str` |
| `test_run_agent_cost_is_non_negative` | `result["cost_usd"] >= 0` |
| `test_run_agent_empty_question_raises` | `run_agent("", ...)` raises `ValueError("question must not be empty")` |
| `test_run_agent_whitespace_only_raises` | `run_agent("   ", ...)` raises `ValueError` |

---

## Ambiguities — resolved

| Ambiguity | Resolution |
|-----------|-----------|
| String shorthand vs `GoogleModel`? | Must use `GoogleModel` + `GoogleProvider` — string shorthand reads `GOOGLE_API_KEY` at `Agent()` construction time, not at `run_sync` time. |
| `result.usage()` or `result.usage`? | Property — confirmed by live test; calling it raises `TypeError`. |
| Token field names? | `input_tokens` / `output_tokens` on `RunUsage` — confirmed by `dir(result.usage)`. |
| `pydantic-ai[gemini]` extra? | No extra exists in 2.21.0. Plain `pydantic-ai` is correct. |

---

## Verification commands (PowerShell)

```powershell
# AC1 — imports cleanly
uv run python -c "from src.agent.agent import create_agent, run_agent; print('OK')"

# AC2 — tests pass (all mocked)
uv run pytest tests/test_agent.py -v

# AC3 — ruff clean
uv run ruff check src/agent/agent.py

# AC4 — live smoke test (costs < $0.001; confirm before running)
uv run python -c "
from src.config import Settings
from src.agent.agent import run_agent
r = run_agent('What is a PaymentIntent?', Settings())
print(r['answer'][:80])
print('tokens in/out:', r['input_tokens'], r['output_tokens'])
print('cost:', r['cost_usd'])
"
```
