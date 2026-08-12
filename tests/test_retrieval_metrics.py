"""Tests for src/eval/retrieval_metrics.py — pure functions, no mocks needed."""

from src.eval.retrieval_metrics import recall_at_k, reciprocal_rank

_IDEAL = ["https://docs.stripe.com/payments/payment-intents"]


# ── recall_at_k ──────────────────────────────────────────────────────────────


def test_recall_returns_one_when_url_present() -> None:
    """First retrieved URL matches ideal → 1.0."""
    retrieved = ["https://docs.stripe.com/payments/payment-intents"]
    assert recall_at_k(retrieved, _IDEAL) == 1.0


def test_recall_returns_zero_when_url_absent() -> None:
    """No retrieved URL matches ideal → 0.0."""
    retrieved = ["https://docs.stripe.com/billing", "https://docs.stripe.com/radar"]
    assert recall_at_k(retrieved, _IDEAL) == 0.0


def test_recall_returns_one_when_match_is_not_first() -> None:
    """Match at position 3 of 3 still returns 1.0 (recall ignores rank)."""
    retrieved = [
        "https://docs.stripe.com/billing",
        "https://docs.stripe.com/radar",
        "https://docs.stripe.com/payments/payment-intents",
    ]
    assert recall_at_k(retrieved, _IDEAL) == 1.0


def test_recall_returns_zero_for_empty_retrieved() -> None:
    """Empty retrieved list → 0.0."""
    assert recall_at_k([], _IDEAL) == 0.0


# ── reciprocal_rank ──────────────────────────────────────────────────────────


def test_reciprocal_rank_first_hit() -> None:
    """Match at rank 1 → 1.0."""
    retrieved = ["https://docs.stripe.com/payments/payment-intents"]
    assert reciprocal_rank(retrieved, _IDEAL) == 1.0


def test_reciprocal_rank_second_hit() -> None:
    """Match at rank 2 → 0.5."""
    retrieved = [
        "https://docs.stripe.com/billing",
        "https://docs.stripe.com/payments/payment-intents",
    ]
    assert reciprocal_rank(retrieved, _IDEAL) == 0.5


def test_reciprocal_rank_no_hit() -> None:
    """No match in retrieved list → 0.0."""
    retrieved = ["https://docs.stripe.com/billing", "https://docs.stripe.com/radar"]
    assert reciprocal_rank(retrieved, _IDEAL) == 0.0
