# Spec 24 — Trace LLM Calls

## Feature
Instrument `run_agent()` in `src/agent/agent.py` to emit a Langfuse trace and
one generation span for every agent turn. The trace captures the user question
and final answer; the generation captures the model name, token counts, and
computed cost. If the Langfuse client is absent (keys not configured), the
function runs exactly as before — no crash, no warning, no behaviour change.

## Why
Feature 23 wired up the Langfuse client factory. This feature uses it for the
first time: every call to `/chat` or `ask.py` will produce a trace visible in
the Langfuse UI, showing what the user asked, what the model replied, how many
tokens were used, and what it cost. Features 25–27 build on top of these traces
to add tool spans, retrieval spans, and session grouping.

## Input contract
- `src/agent/agent.py` — `run_agent()` already returns `input_tokens`,
  `output_tokens`, `cost_usd`
- `src/observability/langfuse_client.py` — `get_langfuse_client(settings)`
  from feature 23

## Output contract

### `src/agent/agent.py` (modify)

`run_agent()` gains Langfuse tracing with this shape:

```
trace  name="stripe-support-chat"
         input=<question>
         output=<answer>
  └── generation  name="gemini-2.5-flash"
                  model="gemini-2.5-flash"
                  input=<question>
                  output=<answer>
                  usage={ "input": input_tokens, "output": output_tokens }
```

- If `get_langfuse_client(settings)` returns `None`, skip all tracing — no
  exceptions, no log lines.
- Trace and generation are created after `run_sync` returns so token counts
  are available.
- `langfuse.flush()` is called at the end of `run_agent` to ensure the event
  is sent before the function returns.
- The return value of `run_agent` is unchanged.

### `tests/test_agent.py` (modify)
Add two new tests:

| Test | Setup | Expected |
|------|-------|---------|
| `test_run_agent_creates_langfuse_trace_when_client_present` | mock `get_langfuse_client` to return a mock client; mock `agent.run_sync` | `client.trace()` called once; `trace.generation()` called with correct model and usage |
| `test_run_agent_skips_tracing_when_client_absent` | mock `get_langfuse_client` to return `None` | no exception; return dict keys unchanged |

## Scope (in)
- `src/agent/agent.py` — add tracing inside `run_agent()`
- `tests/test_agent.py` — two new tests covering trace present / absent

## Scope (out)
- Tool-call spans — feature 25
- Retrieval spans — feature 26
- Session / user grouping on the trace — feature 27
- Any changes to routes, tools, schemas, or config
- `flush()` on app shutdown — feature 27

## Dependencies
- New: none — `langfuse` already added in feature 23
- Existing: `src/observability/langfuse_client.get_langfuse_client`

## Acceptance criteria
1. `uv run pytest tests/test_agent.py -v` passes (all existing tests + 2 new).
2. `uv run ruff check src/agent/agent.py` exits 0.
3. Live smoke test — send one question via `/chat`, open Langfuse UI, confirm
   a trace named `stripe-support-chat` appears with a child generation showing
   the model name and token counts.

## Failure modes to handle
- `get_langfuse_client` returns `None` (keys missing): skip tracing silently,
  return normal result dict.
- `langfuse.flush()` raises (network issue): let the exception propagate — a
  broken observability backend should surface, not be swallowed. (Feature 27
  may revisit this with a timeout.)

## Notes
- Pydantic AI may make multiple internal LLM calls per `run_sync` turn (e.g.
  when a tool result triggers a follow-up generation). We log one aggregate
  generation per `run_agent` call using the totals from `result.usage`. Per-call
  granularity is out of scope for this feature.
- The Langfuse Python SDK v4 `trace()` and `generation()` calls are
  non-blocking — they enqueue events. `flush()` blocks until the queue drains.
- `client.trace()` returns a `StatefulTraceClient`; calling `.generation()`
  on it creates a child span automatically linked to the trace.
