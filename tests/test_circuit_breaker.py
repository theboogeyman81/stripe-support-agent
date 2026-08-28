"""Tests for src/rag/circuit_breaker.py — Redis is always mocked."""

from unittest.mock import MagicMock

from src.rag.circuit_breaker import (
    COOLDOWN_SECONDS,
    FAILURE_THRESHOLD,
    is_circuit_open,
    record_failure,
    record_success,
)


def _mock_redis() -> MagicMock:
    return MagicMock()


def test_closed_when_no_redis():
    assert is_circuit_open(None) is False


def test_closed_when_flag_absent():
    r = _mock_redis()
    r.exists.return_value = 0
    assert is_circuit_open(r) is False


def test_open_when_flag_present():
    r = _mock_redis()
    r.exists.return_value = 1
    assert is_circuit_open(r) is True


def test_open_fails_open_on_redis_error():
    r = _mock_redis()
    r.exists.side_effect = Exception("connection lost")
    assert is_circuit_open(r) is False


def test_record_failure_increments_counter():
    r = _mock_redis()
    r.incr.return_value = 1
    record_failure(r)
    r.incr.assert_called_once_with("cb:failures")


def test_record_failure_opens_circuit_at_threshold():
    r = _mock_redis()
    r.incr.return_value = FAILURE_THRESHOLD
    record_failure(r)
    r.set.assert_called_once_with("cb:open", "1", ex=COOLDOWN_SECONDS)


def test_record_failure_no_open_below_threshold():
    r = _mock_redis()
    r.incr.return_value = FAILURE_THRESHOLD - 1
    record_failure(r)
    r.set.assert_not_called()


def test_record_success_deletes_failures():
    r = _mock_redis()
    record_success(r)
    r.delete.assert_called_once_with("cb:failures")


def test_record_success_does_not_delete_open():
    r = _mock_redis()
    record_success(r)
    calls = [str(c) for c in r.delete.call_args_list]
    assert not any("cb:open" in c for c in calls)


def test_record_failure_noop_when_no_redis():
    record_failure(None)  # must not raise


def test_record_success_noop_when_no_redis():
    record_success(None)  # must not raise
