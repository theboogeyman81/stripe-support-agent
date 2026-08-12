"""Threshold checks for LLM-as-judge eval results."""

import json
from pathlib import Path

import pytest

RESULTS_PATH = Path("data/judge_results.json")


def _load() -> dict:
    if not RESULTS_PATH.exists():
        pytest.skip(f"{RESULTS_PATH} not found — run scripts/run_judge_eval.py first")
    return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))


def test_mean_tool_choice_meets_threshold(thresholds: dict) -> None:
    """mean_tool_choice must be at or above the committed threshold."""
    data = _load()
    assert data["mean_tool_choice"] >= thresholds["mean_tool_choice"], (
        f"mean_tool_choice {data['mean_tool_choice']:.4f} "
        f"< threshold {thresholds['mean_tool_choice']}"
    )


def test_mean_tone_meets_threshold(thresholds: dict) -> None:
    """mean_tone must be at or above the committed threshold."""
    data = _load()
    assert data["mean_tone"] >= thresholds["mean_tone"], (
        f"mean_tone {data['mean_tone']:.4f} < threshold {thresholds['mean_tone']}"
    )
