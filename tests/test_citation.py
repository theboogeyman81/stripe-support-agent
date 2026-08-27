"""Tests for src/guardrails/citation.py — pure unit tests, no network calls."""

from src.guardrails.citation import enforce_citation

_STRIPE_ANSWER = "To create a PaymentIntent, call the PaymentIntents API."
_SOURCE = {"url": "https://docs.stripe.com/payments"}


def test_non_empty_sources_returns_true():
    assert enforce_citation(_STRIPE_ANSWER, [_SOURCE]) is True


def test_empty_sources_real_answer_returns_false():
    assert enforce_citation(_STRIPE_ANSWER, []) is False


def test_empty_answer_empty_sources_returns_true():
    assert enforce_citation("", []) is True


def test_only_stopwords_empty_sources_returns_true():
    assert enforce_citation("the and is to of", []) is True


def test_only_short_words_empty_sources_returns_true():
    # "ok" and "hi" are both <3 chars — no content words
    assert enforce_citation("ok hi", []) is True


def test_multiple_sources_returns_true():
    sources = [_SOURCE, {"url": "https://docs.stripe.com/refunds"}]
    assert enforce_citation(_STRIPE_ANSWER, sources) is True


def test_normal_stripe_answer_with_sources_returns_true():
    assert enforce_citation(_STRIPE_ANSWER, [_SOURCE]) is True
