"""Threshold checks for Ragas eval results."""

import json
from pathlib import Path

import pytest

RESULTS_PATH = Path("data/ragas_results.json")


def _load() -> dict:
    if not RESULTS_PATH.exists():
        pytest.skip(f"{RESULTS_PATH} not found — run scripts/run_ragas_eval.py first")
    return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))


def test_faithfulness_meets_threshold(thresholds: dict) -> None:
    """faithfulness must be at or above the committed threshold."""
    data = _load()
    assert data["faithfulness"] >= thresholds["faithfulness"], (
        f"faithfulness {data['faithfulness']:.4f} < threshold "
        f"{thresholds['faithfulness']}"
    )


def test_context_precision_meets_threshold(thresholds: dict) -> None:
    """context_precision must be at or above the committed threshold."""
    data = _load()
    assert data["context_precision"] >= thresholds["context_precision"], (
        f"context_precision {data['context_precision']:.4f} "
        f"< threshold {thresholds['context_precision']}"
    )


def test_answer_relevancy_meets_threshold(thresholds: dict) -> None:
    """answer_relevancy must be at or above the committed threshold."""
    data = _load()
    assert data["answer_relevancy"] >= thresholds["answer_relevancy"], (
        f"answer_relevancy {data['answer_relevancy']:.4f} "
        f"< threshold {thresholds['answer_relevancy']}"
    )
