"""Shared fixtures for the eval test suite."""

import json
from pathlib import Path

import pytest

THRESHOLDS_PATH = Path("data/eval_thresholds.json")


@pytest.fixture(scope="session")
def thresholds() -> dict:
    """Load eval_thresholds.json once for the entire session."""
    return json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
