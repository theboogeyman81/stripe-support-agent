"""Tests for scripts/check_regression.py — pure functions, no file I/O."""

from scripts.check_regression import check_regressions, format_report

_BASELINE = {
    "recall_at_k": 0.70,
    "mrr": 0.55,
    "faithfulness": 0.55,
    "context_precision": 0.50,
    "answer_relevancy": 0.55,
    "mean_tool_choice": 0.75,
    "mean_tone": 0.75,
}

_DELTA = 0.05


def _current_above() -> dict[str, float | None]:
    return {k: v + 0.10 for k, v in _BASELINE.items()}


def test_ok_when_scores_above_baseline() -> None:
    """All current scores above baseline → all rows are OK."""
    rows = check_regressions(_current_above(), _BASELINE, _DELTA)
    assert all(r["status"] == "OK" for r in rows)


def test_regression_when_drop_exceeds_delta() -> None:
    """Score dropping more than delta below baseline → REGRESSION."""
    current = _current_above()
    current["recall_at_k"] = _BASELINE["recall_at_k"] - _DELTA - 0.01
    rows = check_regressions(current, _BASELINE, _DELTA)
    recall_row = next(r for r in rows if r["metric"] == "recall_at_k")
    assert recall_row["status"] == "REGRESSION"


def test_ok_when_drop_within_delta() -> None:
    """Score exactly at baseline − delta is not a regression (boundary case)."""
    current = _current_above()
    current["recall_at_k"] = _BASELINE["recall_at_k"] - _DELTA
    rows = check_regressions(current, _BASELINE, _DELTA)
    recall_row = next(r for r in rows if r["metric"] == "recall_at_k")
    assert recall_row["status"] == "OK"


def test_skip_when_current_is_none() -> None:
    """None current value → SKIP status, never REGRESSION."""
    current = _current_above()
    current["mrr"] = None
    rows = check_regressions(current, _BASELINE, _DELTA)
    mrr_row = next(r for r in rows if r["metric"] == "mrr")
    assert mrr_row["status"] == "SKIP"
    assert mrr_row["current"] is None
    assert mrr_row["delta"] is None


def test_format_report_contains_metric_names() -> None:
    """All baseline metric names appear in the formatted report."""
    rows = check_regressions(_current_above(), _BASELINE, _DELTA)
    report = format_report(rows)
    for metric in _BASELINE:
        assert metric in report


def test_format_report_shows_regression_label() -> None:
    """REGRESSION label appears in output when a metric has regressed."""
    current = _current_above()
    current["mean_tone"] = 0.0
    rows = check_regressions(current, _BASELINE, _DELTA)
    report = format_report(rows)
    assert "REGRESSION" in report
