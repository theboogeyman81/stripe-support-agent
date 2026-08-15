"""Tests for scripts/write_eval_summary.py — no file I/O."""

from scripts.write_eval_summary import build_rows, format_table

_THRESHOLDS = {
    "recall_at_k": 0.50,
    "mrr": 0.35,
    "faithfulness": 0.40,
    "context_precision": 0.40,
    "answer_relevancy": 0.40,
    "mean_tool_choice": 0.60,
    "mean_tone": 0.60,
}

_ALL_RESULTS = {
    "retrieval_results.json": {"recall_at_k": 0.80, "mrr": 0.70},
    "ragas_results.json": {
        "faithfulness": 0.60,
        "context_precision": 0.55,
        "answer_relevancy": 0.55,
    },
    "judge_results.json": {"mean_tool_choice": 0.80, "mean_tone": 0.75},
}


def test_build_rows_all_files_present() -> None:
    """All 7 rows populated with scores and PASS statuses when all files present."""
    rows = build_rows(_ALL_RESULTS, _THRESHOLDS)
    assert len(rows) == 7
    assert all(r["score"] is not None for r in rows)
    assert all(r["status"] == "PASS" for r in rows)


def test_build_rows_missing_file_produces_na() -> None:
    """Missing result file yields N/A score and — status for its metrics."""
    results = dict(_ALL_RESULTS)
    results["retrieval_results.json"] = None
    rows = build_rows(results, _THRESHOLDS)
    retrieval = [r for r in rows if r["metric"] in ("recall_at_k", "mrr")]
    assert all(r["score"] is None for r in retrieval)
    assert all(r["status"] == "—" for r in retrieval)


def test_build_rows_below_threshold_is_fail() -> None:
    """Score below threshold yields FAIL status."""
    results = dict(_ALL_RESULTS)
    results["retrieval_results.json"] = {"recall_at_k": 0.10, "mrr": 0.05}
    rows = build_rows(results, _THRESHOLDS)
    recall_row = next(r for r in rows if r["metric"] == "recall_at_k")
    assert recall_row["status"] == "FAIL"


def test_format_table_contains_header() -> None:
    """Output includes the markdown table header row."""
    rows = build_rows(_ALL_RESULTS, _THRESHOLDS)
    table = format_table(rows)
    assert "| Metric |" in table


def test_format_table_contains_all_metrics() -> None:
    """All 7 metric names appear in the formatted table."""
    rows = build_rows(_ALL_RESULTS, _THRESHOLDS)
    table = format_table(rows)
    for metric in (
        "recall_at_k", "mrr", "faithfulness",
        "context_precision", "answer_relevancy",
        "mean_tool_choice", "mean_tone",
    ):
        assert metric in table
