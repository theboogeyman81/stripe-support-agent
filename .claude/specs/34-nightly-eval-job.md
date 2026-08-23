# Spec 34 — Nightly Eval Job

## Feature
A GitHub Actions workflow (`.github/workflows/nightly-eval.yml`) that runs on
a nightly cron schedule and on `workflow_dispatch` (manual trigger). It:

1. Runs all three eval runner scripts in sequence (`run_retrieval_eval.py`,
   `run_ragas_eval.py`, `run_judge_eval.py`) — each with `--yes` to skip the
   cost prompt.
2. Runs `pytest tests/eval/` to enforce thresholds (fails the job if any
   score drops below its committed threshold).
3. Uploads the three result JSON files as a single GitHub Actions artifact.
4. Writes a score summary table to the GitHub Actions job summary
   (`$GITHUB_STEP_SUMMARY`) so scores are visible in the Actions UI without
   downloading the artifact.

## Why
The eval scripts (features 30–32) and the pytest threshold suite (feature 33)
exist but run only manually. The nightly job automates this: any PR that
degrades retrieval or generation quality will fail CI on the next nightly run,
closing the eval feedback loop. The job summary makes scores visible at a
glance in the GitHub Actions UI.

## Input contract
- GitHub repository secrets (required):
  - `GEMINI_API_KEY`
  - `VOYAGE_API_KEY`
  - `QDRANT_URL`
  - `QDRANT_API_KEY`
- `data/golden_dataset.jsonl` — committed to the repo, available on checkout.
- `data/eval_thresholds.json` — committed to the repo.

## Output contract
- **GitHub Actions artifact** named `eval-results-<run-id>`, retained 30 days,
  containing:
  - `data/retrieval_results.json`
  - `data/ragas_results.json`
  - `data/judge_results.json`
- **Job summary** written to `$GITHUB_STEP_SUMMARY` (visible in the Actions UI)
  with a markdown table of all 7 metric scores vs thresholds, and a pass/fail
  indicator per row.

## Scope (in)
- `.github/workflows/nightly-eval.yml` — the workflow file.
- `scripts/write_eval_summary.py` — new helper script: reads the three result
  files and `eval_thresholds.json`, writes a markdown table to stdout, which
  the workflow redirects to `$GITHUB_STEP_SUMMARY`.

## Scope (out)
- No changes to any eval script or test file.
- No GitHub Pages deployment.
- No Slack or email notification.
- No regression detection logic (that is feature 35).
- No Langfuse integration in CI.

## Dependencies
- New: none. Uses existing eval scripts and `uv` package manager.
- Existing: features 30–33 scripts and tests; `data/eval_thresholds.json`.

## Acceptance criteria
1. `.github/workflows/nightly-eval.yml` exists and is valid YAML:
   ```powershell
   python -c "import yaml; yaml.safe_load(open('.github/workflows/nightly-eval.yml'))"
   ```
   (requires `pip install pyyaml` or `uv run python -c ...` after adding pyyaml
   to dev deps — alternatively, just push and let GitHub validate it).
2. Workflow has `schedule: cron: '0 2 * * *'` and `workflow_dispatch` triggers.
3. `uv run python -m scripts.write_eval_summary --help` exits 0.
4. `uv run pytest tests/test_write_eval_summary.py -v` — all tests pass.
5. (Manual) Trigger the workflow via GitHub UI `workflow_dispatch`; verify it
   completes, uploads an artifact, and shows the score table in the job summary.

## Failure modes to handle
- An eval script exits non-zero (e.g. Qdrant unreachable): the step fails,
  the job fails. Subsequent steps still run because artifact upload uses
  `if: always()`, so whatever results exist are still uploaded.
- A result file is absent when `write_eval_summary.py` runs: print `N/A` for
  that file's metrics in the summary table; do not exit non-zero.
- `pytest tests/eval/` exits non-zero (threshold breach): the job fails.
  Artifact upload still runs (`if: always()`).

## Notes
- pydantic-settings reads env vars in addition to `.env`; on CI there is no
  `.env` file, so all required vars must be set as repository secrets and
  passed via the workflow `env:` block.
- The workflow runs on `ubuntu-latest`. `uv` is installed via the official
  `astral-sh/setup-uv@v4` action.
- Artifact retention is 30 days (GitHub default) — no explicit override needed.
- `write_eval_summary.py` writes **only to stdout**, making it testable without
  touching `$GITHUB_STEP_SUMMARY`. The workflow redirects stdout to the
  summary file: `uv run python -m scripts.write_eval_summary >> $GITHUB_STEP_SUMMARY`.
- Cron `0 2 * * *` = 2:00 AM UTC daily, chosen to run outside peak hours and
  after any nightly deploys.
