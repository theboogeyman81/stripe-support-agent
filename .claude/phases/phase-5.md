# Phase 5 — Evaluation pipeline

> Draft.

## Goal
Automated evaluation of retrieval and generation quality, wired into CI so
regressions block merges.

## Features (planned)
29. `golden-dataset` — 30–50 curated Q/A pairs with ideal doc URLs
30. `ragas-integration` — faithfulness, context precision, answer relevancy
31. `llm-as-judge` — custom judge for agent behaviour (tool choice, tone)
32. `retrieval-eval` — recall@k, MRR against golden dataset
33. `pytest-eval-suite` — evals run as tests, thresholds enforced
34. `nightly-eval-job` — GitHub Actions cron, publishes report
35. `regression-detection` — compare against baseline, alert on drop

## What you'll learn
- Building datasets when there's no ground truth
- LLM-as-judge design (rubrics, calibration, judge bias)
- Choosing eval metrics that actually correlate with user-perceived quality
- Wiring evals into CI without making CI unbearably slow

## Exit checklist
- [ ] Golden dataset committed with per-item ideal URLs
- [ ] `uv run pytest tests/eval/` runs all evals and reports scores
- [ ] Baseline scores recorded in repo
- [ ] Nightly job publishes report artifact
- [ ] PR that intentionally degrades retrieval fails CI
- [ ] `LEARNINGS.md` updated with Phase 5 notes