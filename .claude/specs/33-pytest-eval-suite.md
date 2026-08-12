# Spec 33 — Pytest Eval Suite

## Feature
A `tests/eval/` directory containing three pytest test files that enforce
minimum score thresholds on the evaluation results produced by features 30–32.
The tests **read from result JSON files** written by the runner scripts; they
do not re-invoke live APIs. If a result file is absent, the test skips with a
clear message.

Thresholds are stored in `data/eval_thresholds.json` (committed). When the
nightly job (feature 34) runs the eval scripts and then runs
`pytest tests/eval/`, any score that has dropped below its threshold causes
the build to fail.

## Why
Features 30–32 produce standalone scripts and result files but nothing enforces
quality gates. Wrapping the threshold checks in pytest means the same `pytest`
command used in CI can catch regressions. The read-from-file design keeps the
eval tests fast and API-free; the nightly job (feature 34) is responsible for
refreshing the result files before running the suite.

## Input contract
Result files written by the runner scripts (all in `data/`):

| File | Written by |
|------|-----------|
| `data/retrieval_results.json` | `scripts/run_retrieval_eval.py` |
| `data/ragas_results.json` | `scripts/run_ragas_eval.py` |
| `data/judge_results.json` | `scripts/run_judge_eval.py` |

Each file's schema is defined in its feature spec (32, 30, 31 respectively).

Threshold file `data/eval_thresholds.json` (committed, conservative initial
values to be updated after first live run):
```json
{
  "recall_at_k": 0.50,
  "mrr": 0.35,
  "faithfulness": 0.40,
  "context_precision": 0.40,
  "answer_relevancy": 0.40,
  "mean_tool_choice": 0.60,
  "mean_tone": 0.60
}
```

## Output contract
No files written. Pytest pass/fail is the output.

## Scope (in)
- `tests/eval/__init__.py` — empty package marker.
- `tests/eval/conftest.py` — loads `data/eval_thresholds.json` once; exposes
  a `thresholds` fixture available to all tests in this directory.
- `tests/eval/test_retrieval.py` — 2 tests: `recall_at_k` and `mrr` against
  thresholds. Skips if `data/retrieval_results.json` is absent.
- `tests/eval/test_ragas.py` — 3 tests: `faithfulness`, `context_precision`,
  `answer_relevancy`. Skips if `data/ragas_results.json` is absent.
- `tests/eval/test_judge.py` — 2 tests: `mean_tool_choice`, `mean_tone`.
  Skips if `data/judge_results.json` is absent.
- `data/eval_thresholds.json` — committed threshold values.
- `pyproject.toml` — add `markers` entry for the `eval` mark so ruff/pytest
  does not warn about unknown marks; add `testpaths = ["tests"]` so default
  `uv run pytest` does not collect `tests/eval/` automatically.

## Scope (out)
- No live API calls inside any test.
- No changes to the runner scripts (30–32).
- No threshold auto-update logic (human updates `eval_thresholds.json` after
  reviewing a new baseline).
- No HTML/artifact report generation (that belongs in feature 34).

## Dependencies
- New: none.
- Existing: `data/eval_thresholds.json` (created here),
  result files from features 30–32 (must exist before tests run).

## Acceptance criteria
1. `uv run pytest tests/eval/ -v` — all 7 tests **skip** (result files absent)
   with a message containing `"not found"`.
2. `uv run pytest -q` (default run) — `tests/eval/` is **not collected**
   (zero eval tests in the output).
3. `uv run ruff check tests/eval/` — no errors.
4. (With result files present) place a `data/retrieval_results.json` with
   `recall_at_k: 0.0` and run `uv run pytest tests/eval/test_retrieval.py -v`
   — the `test_recall_at_k_meets_threshold` test **fails**.
5. (With result files present) place a `data/retrieval_results.json` with
   scores above thresholds — both retrieval tests **pass**.

## Failure modes to handle
- Result file absent: `pytest.skip(f"data/X_results.json not found — run the eval script first")`.
- Result file present but malformed JSON: let the `json.loads` exception
  propagate (test errors, not skips — indicates a broken pipeline).
- Threshold file absent: raise `FileNotFoundError` immediately (the threshold
  file is committed and must always exist).

## Notes
- `testpaths = ["tests"]` in `pyproject.toml` means `uv run pytest` only
  collects from `tests/` (not `tests/eval/`). To run the eval suite explicitly:
  `uv run pytest tests/eval/`. Feature 34's CI step will call this explicitly
  after running the eval scripts.
- The `thresholds` fixture is session-scoped (`scope="session"`) — the JSON
  file is loaded once per pytest session, not once per test.
- Conservative initial thresholds (all ≥ 0.40 for generation, ≥ 0.50 for
  retrieval recall) are intentionally low so they pass even on a first run
  with a partial index. Update them upward after confirming real baseline
  scores.
- The `eval` mark is registered in `pyproject.toml` under
  `[tool.pytest.ini_options]` to suppress `PytestUnknownMarkWarning`, but
  tests in `tests/eval/` are not decorated with `@pytest.mark.eval` — the
  directory-based separation is sufficient for this project.
