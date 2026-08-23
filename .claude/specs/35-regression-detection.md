# Spec 35 — Regression Detection

## Feature
A script (`scripts/check_regression.py`) that compares the current eval result
files against a committed baseline (`data/eval_baseline.json`) and exits
non-zero if any metric has dropped by more than a configurable delta (default
0.05). The nightly workflow (feature 34) gets a new "Check for regressions"
step that runs this script after the evals complete.

## Why
`eval_thresholds.json` enforces absolute minimums but cannot catch gradual
degradation. Scores might drop from 0.90 to 0.72 without ever breaching the
0.50 threshold. Regression detection flags drops relative to the last known-good
baseline, surfacing changes that are meaningful even if they stay above the
floor. The human explicitly updates the baseline after confirming a good run,
which prevents auto-ratcheting to a bad state.

## Input contract
- `data/eval_baseline.json` — committed, human-maintained:
  ```json
  {
    "recall_at_k": 0.70,
    "mrr": 0.55,
    "faithfulness": 0.55,
    "context_precision": 0.50,
    "answer_relevancy": 0.55,
    "mean_tool_choice": 0.75,
    "mean_tone": 0.75
  }
  ```
  (Initial values are conservative placeholders; human raises them after first
  live run.)
- Current result files in `data/`:
  - `retrieval_results.json` (keys: `recall_at_k`, `mrr`)
  - `ragas_results.json` (keys: `faithfulness`, `context_precision`, `answer_relevancy`)
  - `judge_results.json` (keys: `mean_tool_choice`, `mean_tone`)

## Output contract
- Stdout: a comparison table printed for every metric (score, baseline, delta,
  status). Example:
  ```
  Metric              Baseline  Current  Delta    Status
  recall_at_k         0.7000    0.8500   +0.1500  OK
  mrr                 0.5500    0.3800   -0.1700  REGRESSION
  faithfulness        0.5500    N/A      —        SKIP
  ```
- Exit code 0 if no regressions detected; exit code 1 if one or more metrics
  regressed beyond the delta threshold.

## Scope (in)
- `data/eval_baseline.json` — new committed file with initial placeholder values.
- `scripts/check_regression.py` — new script:
  - `load_current(data_dir: Path) -> dict[str, float | None]` — loads all 7
    metric values from the three result files; `None` for missing files/keys.
  - `check_regressions(current, baseline, delta) -> list[dict]` — pure function;
    returns one row per metric with keys `metric`, `baseline`, `current`,
    `delta`, `status` (`"OK"`, `"REGRESSION"`, `"SKIP"`).
  - `format_report(rows) -> str` — returns the printed comparison table.
  - `main()` — argparse with `--delta` (float, default 0.05) and `--data-dir`
    (Path, default `data/`); exits 1 on any regression.
- `tests/test_check_regression.py` — new test file, 6 tests, no file I/O.
- `.github/workflows/nightly-eval.yml` — add "Check for regressions" step after
  "Enforce thresholds", before "Write job summary".

## Scope (out)
- No automatic baseline update logic.
- No Slack/email alert (CI failure is the alert mechanism).
- No per-metric delta configuration (one global delta for all metrics).
- No changes to any other eval script or test file.

## Dependencies
- New: none.
- Existing: `data/eval_baseline.json` (created here), result files from
  features 30–32.

## Acceptance criteria
1. `uv run python -m scripts.check_regression --help` exits 0 and shows
   `--delta` and `--data-dir` flags.
2. `uv run pytest tests/test_check_regression.py -v` — all tests pass.
3. `uv run ruff check scripts/check_regression.py tests/test_check_regression.py`
   — no errors.
4. With a synthetic `data/retrieval_results.json` containing
   `recall_at_k: 0.40` (below baseline 0.70 by 0.30 > delta 0.05):
   ```powershell
   # write synthetic file, run script, expect exit 1
   uv run python -m scripts.check_regression
   echo "exit code: $LASTEXITCODE"   # expect 1
   ```
5. With `recall_at_k: 0.72` in the result file (above baseline 0.70, delta
   +0.02 within tolerance):
   ```powershell
   uv run python -m scripts.check_regression
   echo "exit code: $LASTEXITCODE"   # expect 0
   ```

## Failure modes to handle
- A result file is absent: mark its metrics as `"SKIP"` — do not count as
  regression, do not exit 1.
- `eval_baseline.json` is absent: print a warning and exit 0 (skip regression
  check entirely — handles the bootstrap case before a baseline is set).
- All metrics are `"SKIP"` (no result files at all): print warning, exit 0.

## Notes
- Delta comparison: `regression = current < baseline - delta`. A score of 0.65
  with baseline 0.70 and delta 0.05 is NOT a regression (0.65 >= 0.65). A
  score of 0.64 IS a regression (0.64 < 0.65).
- The `check_regressions` function is pure (no I/O) so it can be tested
  directly with inline dicts — same pattern as `write_eval_summary.py`.
- The nightly workflow step uses `if: always()` so the regression report is
  printed even when `pytest tests/eval/` already failed a threshold check.
- The seven metrics and their source files are the same as in
  `write_eval_summary.py` — reuse the `METRICS` constant by importing from
  that module rather than duplicating it.
