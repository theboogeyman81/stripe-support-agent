"""Tests for scripts/validate_golden_dataset.py — no file I/O except missing-file test.
"""

import json
from unittest.mock import patch

import pytest

from scripts.validate_golden_dataset import main, validate_records


def _lines(*records: dict) -> list[str]:
    return [json.dumps(r) for r in records]


def _good(id: str = "q001") -> dict:
    return {
        "id": id,
        "question": "What is a PaymentIntent?",
        "reference_answer": "A PaymentIntent tracks a payment lifecycle.",
        "ideal_urls": ["https://docs.stripe.com/payments/payment-intents"],
    }


def test_valid_records_returns_no_errors() -> None:
    """Three well-formed records produce zero errors and total==3."""
    total, errors = validate_records(
        _lines(_good("q001"), _good("q002"), _good("q003"))
    )
    assert errors == []
    assert total == 3


def test_malformed_json_is_caught() -> None:
    """A line that is not valid JSON produces an error mentioning 'invalid JSON'."""
    total, errors = validate_records(["{not json"])
    assert total == 1
    assert len(errors) == 1
    assert "invalid JSON" in errors[0]


def test_missing_required_field_is_caught() -> None:
    """A record missing 'reference_answer' produces an error mentioning the field."""
    rec = _good()
    del rec["reference_answer"]
    _, errors = validate_records(_lines(rec))
    assert len(errors) == 1
    assert "missing fields" in errors[0]
    assert "reference_answer" in errors[0]


def test_duplicate_id_is_caught() -> None:
    """Two records sharing the same id produce an error mentioning 'duplicate id'."""
    _, errors = validate_records(_lines(_good("q001"), _good("q001")))
    assert any("duplicate id" in e for e in errors)


def test_invalid_id_format_is_caught() -> None:
    """An id not matching q<NNN> produces an error mentioning 'must match q<NNN>'."""
    rec = _good()
    rec["id"] = "001"
    _, errors = validate_records(_lines(rec))
    assert any("must match q<NNN>" in e for e in errors)


def test_empty_question_is_caught() -> None:
    """A blank 'question' field produces an error mentioning 'non-empty string'."""
    rec = _good()
    rec["question"] = "   "
    _, errors = validate_records(_lines(rec))
    assert any("non-empty string" in e for e in errors)


def test_too_many_ideal_urls_is_caught() -> None:
    """A record with 4 ideal_urls produces an error mentioning '1–3 items'."""
    rec = _good()
    rec["ideal_urls"] = ["https://a.com", "https://b.com", "https://c.com", "https://d.com"]
    _, errors = validate_records(_lines(rec))
    assert any("1–3 items" in e for e in errors)


def test_missing_file_exits_nonzero(tmp_path: pytest.TempPathFactory) -> None:
    """Passing a nonexistent path to main() must raise SystemExit with code 1."""
    missing = tmp_path / "nope.jsonl"
    with patch("sys.argv", ["validate", "--path", str(missing)]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
