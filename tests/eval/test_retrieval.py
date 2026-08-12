"""Threshold checks for retrieval eval results."""

import json
from pathlib import Path

import pytest

RESULTS_PATH = Path("data/retrieval_results.json")


def _load() -> dict:
    if not RESULTS_PATH.exists():
        pytest.skip(f"{RESULTS_PATH} not found — run run_retrieval_eval.py first")
    return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))


def test_recall_at_k_meets_threshold(thresholds: dict) -> None:
    """recall_at_k must be at or above the committed threshold."""
    data = _load()
    assert data["recall_at_k"] >= thresholds["recall_at_k"], (
        f"recall_at_k {data['recall_at_k']:.4f} < threshold {thresholds['recall_at_k']}"
    )


def test_mrr_meets_threshold(thresholds: dict) -> None:
    """mrr must be at or above the committed threshold."""
    data = _load()
    assert data["mrr"] >= thresholds["mrr"], (
        f"mrr {data['mrr']:.4f} < threshold {thresholds['mrr']}"
    )
