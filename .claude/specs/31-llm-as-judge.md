# Spec 31 — LLM-as-Judge

## Feature
A custom LLM judge that scores two dimensions of agent behaviour for each
question in the golden dataset:

1. **Tool choice** — did the agent invoke the right tool(s) given the question?
2. **Tone** — was the answer concise, honest, and professional?

`src/eval/judge.py` holds two rubric prompt templates and two scoring functions
(`score_tool_choice`, `score_tone`) that each call Gemini and return a float
(0.0, 0.5, or 1.0) plus a rationale string.

`scripts/run_judge_eval.py` is the runner: it loads the golden dataset, runs
`run_agent()` on each question, extracts tool names from the returned message
history, calls both judge functions, aggregates, and writes
`data/judge_results.json`.

## Why
Ragas measures whether the retrieved context supports the answer (faithfulness)
and whether the answer is relevant (answer relevancy). It says nothing about
agent behaviour: whether the right tool was called, whether the agent invented
an answer without searching docs, or whether the tone drifted from professional
to overly casual. The LLM-as-judge fills that gap and produces two additional
baseline scores that feature 33 (pytest-eval-suite) will enforce as thresholds.

## Input contract
- `data/golden_dataset.jsonl` — JSONL, one record per line:
  ```json
  {
    "id": "q001",
    "question": "...",
    "reference_answer": "...",
    "ideal_urls": ["..."]
  }
  ```
- Agent message history from `run_agent()["message_history"]` — JSON-serialised
  Pydantic AI messages. Tool calls appear in `ModelResponse` parts with
  `"part_kind": "tool-call"` and a `"tool_name"` field.

## Output contract
`data/judge_results.json`:
```json
{
  "items": [
    {
      "id": "q001",
      "question": "...",
      "tools_called": ["search_docs"],
      "answer": "...",
      "tool_choice_score": 1.0,
      "tone_score": 0.8,
      "tool_choice_rationale": "search_docs was the correct tool for a doc question.",
      "tone_rationale": "Answer is concise and professional."
    }
  ],
  "mean_tool_choice": 0.92,
  "mean_tone": 0.85,
  "items_evaluated": 40,
  "items_skipped": 0,
  "generate_cost_usd": 0.0012,
  "judge_cost_usd": 0.0030,
  "timestamp": "2026-08-12T10:00:00+00:00"
}
```

Field rules:
- `tool_choice_score` / `tone_score`: one of `0.0`, `0.5`, `1.0` only.
- `tools_called`: list of tool name strings, may be empty if no tool was invoked.
- `generate_cost_usd`: sum of `cost_usd` from each `run_agent()` call.
- `judge_cost_usd`: estimated cost of the judge LLM calls (2 calls × n items).
- `timestamp`: ISO-8601, UTC.

## Scope (in)
- `src/eval/judge.py` — new file:
  - `TOOL_CHOICE_PROMPT` template string
  - `TONE_PROMPT` template string
  - `extract_tool_calls(message_history: list[dict]) -> list[str]`
  - `score_tool_choice(question: str, tools_called: list[str], answer: str, client: genai.Client, model: str) -> dict` — returns `{"score": float, "rationale": str}`
  - `score_tone(question: str, answer: str, client: genai.Client, model: str) -> dict` — returns `{"score": float, "rationale": str}`
- `scripts/run_judge_eval.py` — new runner script (same cost-confirm pattern as `run_ragas_eval.py`).
- `tests/test_judge.py` — new test file.

## Scope (out)
- No changes to `run_agent()`, `agent.py`, or any tool file.
- No Langfuse integration — scores are written to disk only.
- No per-item expected-tool field in the golden dataset (the judge infers correctness from question context and the system prompt's tool-selection rules).
- No async evaluation.
- No changes to `run_ragas_eval.py`.

## Dependencies
- New: none. Uses `google-genai` (already installed) and the existing `src/eval/` package.
- Existing: `src/agent/agent.py` (`run_agent`), `src/config.py` (`Settings`), `data/golden_dataset.jsonl`.

## Acceptance criteria
1. `uv run python scripts/run_judge_eval.py --help` exits 0 and lists `--path`, `--top-k`, `--yes` flags.
2. `uv run pytest tests/test_judge.py -v` — all tests pass with zero network calls.
3. `uv run ruff check src/eval/judge.py scripts/run_judge_eval.py` — no errors.
4. (Live APIs) `uv run python scripts/run_judge_eval.py --yes` exits 0, writes `data/judge_results.json`, and that file passes:
   ```powershell
   python -c "import json; d=json.load(open('data/judge_results.json')); assert 'mean_tool_choice' in d and 'mean_tone' in d"
   ```

## Failure modes to handle
- `run_agent()` raises: print warning, skip item, increment `items_skipped`.
- Judge Gemini call returns text that is not valid JSON: record `score=0.5` and `rationale="parse error"` for that dimension; do not skip the item.
- No items evaluated at all: print error and `sys.exit(1)`.

## Notes
- The judge prompt must instruct Gemini to respond with **only** a JSON object
  and nothing else:
  ```
  {"score": 0|0.5|1, "rationale": "<one sentence>"}
  ```
  No markdown fences. Keep parsing to a simple `json.loads()` call.
- Tool-call extraction logic: iterate `message_history` (list of dicts), check
  each item's `"parts"` list for dicts with `"part_kind": "tool-call"`, collect
  the `"tool_name"` value. This matches the shape produced by
  `ModelMessagesTypeAdapter.dump_python()`.
- Tool-choice rubric: the prompt includes the question, the list of tools
  called, and the system prompt's tool-selection rules (copied verbatim) so the
  judge has the same contract the agent was given.
- Tone rubric: the prompt includes the question and the answer only. Scoring
  guide — 1.0: concise, honest, professional; 0.5: minor issues (slightly too
  long, hedging without cause, minor informality); 0.0: hallucination,
  off-topic, rude, or clearly wrong.
- Cost estimate: 1 agent call (~8 LLM calls internally) + 2 judge calls per
  item. Judge calls: ~600 input + 80 output tokens each. Total for 40 items ≈
  $0.10, well within budget.
- Score is intentionally coarse (0 / 0.5 / 1) — continuous floats from an LLM
  judge carry false precision and vary too much between runs to be meaningful
  thresholds.
