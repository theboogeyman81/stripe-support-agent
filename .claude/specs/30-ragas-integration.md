# Spec 30 — Ragas Integration

## Feature
Add a `scripts/run_ragas_eval.py` script that runs three Ragas generation-quality
metrics — **faithfulness**, **context precision**, and **answer relevancy** — over
the golden dataset. For each item in `data/golden_dataset.jsonl`, the script calls
the existing `retrieve()` and `generate()` functions to produce contexts and an
answer, then feeds those into Ragas. Results are printed as a score table and
saved to `data/ragas_results.json` (gitignored).

## Why
Ragas gives us automatic, LLM-graded measures of two key failure modes: hallucination
(faithfulness) and irrelevant responses (answer relevancy). Context precision
measures whether retrieved chunks are actually useful. Together they form the
generation-quality baseline that feature 33 will enforce as CI thresholds.

## Input contract
- `data/golden_dataset.jsonl` — from feature 29; fields `question` and
  `reference_answer` used here
- `src/rag/vectorstore.retrieve(query, top_k)` — returns `list[dict]` with
  `text`, `doc_title`, `doc_url`
- `src/rag/generator.generate(question, chunks)` — returns `dict` with `answer`,
  `input_tokens`, `output_tokens`, `cost_usd`
- `src/config.Settings` — for `gemini_api_key`; loaded once at script start

## Output contract

### stdout (always)
```
Estimated cost: $X.XX USD  (N items × ~M LLM calls each)
Proceed? [y/N]:
```
Then after confirmation:
```
  faithfulness        0.82
  context_precision   0.74
  answer_relevancy    0.89
  items_evaluated     40
  total_cost_usd      0.031
```

### `data/ragas_results.json` (written on success)
```json
{
  "faithfulness": 0.82,
  "context_precision": 0.74,
  "answer_relevancy": 0.89,
  "items_evaluated": 40,
  "total_cost_usd": 0.031,
  "timestamp": "2026-08-08T12:00:00Z"
}
```
`data/ragas_results.json` must be gitignored (already covered by `data/` rule
except the JSONL exception — the JSON file stays excluded).

## Scope (in)
- `scripts/run_ragas_eval.py` — the eval runner
- `src/eval/__init__.py` — empty, marks the package
- `src/eval/ragas_llm.py` — thin `BaseRagasLLM` subclass wrapping our
  `google-genai` client (needed because we cannot use LangChain)
- `tests/test_ragas_llm.py` — unit tests for the wrapper (mocked genai client)
- `pyproject.toml` — add `ragas` to dependencies

## Scope (out)
- Evaluating the full Pydantic AI agent — this feature evaluates the RAG pipeline
  (retrieve + generate) only; agent eval is for feature 31
- Per-item scores saved to disk — only aggregate scores in this feature
- HTML/chart reports — plain JSON only
- Running on every PR in CI — that is feature 33

## Dependencies
- New: `ragas` (approved in CLAUDE.md tech stack as "Ragas + custom LLM-as-judge")
- Existing: `google-genai`, `src.rag.vectorstore.retrieve`,
  `src.rag.generator.generate`, `src.config.Settings`

## Acceptance criteria
1. `uv run python scripts/run_ragas_eval.py --yes` completes without error,
   prints a score table, and exits 0. (`--yes` bypasses the cost confirmation
   prompt for automation.)
2. `data/ragas_results.json` exists after running and contains the four numeric
   fields.
3. `uv run pytest tests/test_ragas_llm.py -v` passes.
4. `uv run pytest -q` — full suite passes with no regressions.

## Failure modes to handle
- `data/golden_dataset.jsonl` not found: print error and exit 1.
- `retrieve()` returns empty list for an item: skip that item, log a warning,
  continue; include `items_skipped` count in the results.
- Ragas metric computation raises: print the error, skip the item, continue.
- User answers `n` (or presses Enter) at the cost prompt: exit 0 with message
  "Aborted."

## Notes
- **Critical constraint:** we use `google-genai` SDK, not LangChain. Ragas's
  default LLM integrations go through `LangchainLLMWrapper`. The planner must
  verify the `ragas.llms.base.BaseRagasLLM` interface (or equivalent in the
  pinned Ragas version) and implement a custom subclass wrapping `genai.Client`.
- Pin the ragas version in `pyproject.toml` (e.g. `ragas>=0.2,<0.3`) and
  confirm the API during planning — the 0.1→0.2 migration was breaking.
- Ragas metrics that use an LLM internally (faithfulness, answer_relevancy,
  context_precision) will each make additional Gemini calls. Cost estimate
  should assume ~3 extra Gemini calls per item on top of the 1 generate() call.
- `--yes` flag must bypass only the confirmation prompt, not any other safety
  checks.
- The eval uses `top_k=5` (same as the production default) so scores reflect
  real retrieval behaviour.
