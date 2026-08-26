"""Tests for src/guardrails/hallucination.py — pure unit tests, no network calls."""

from src.guardrails.hallucination import (
    UNGROUNDED_FALLBACK,
    GroundingResult,
    check_grounding,
)

_STRIPE_CHUNK = {
    "text": (
        "To create a PaymentIntent, call the PaymentIntents API with the amount "
        "and currency. The PaymentIntent tracks the lifecycle of a payment."
    )
}

_COOKING_CHUNK = {"text": "Mix flour, eggs, and butter. Bake at 180 degrees."}


def test_grounded_answer():
    answer = "You can create a PaymentIntent using the PaymentIntents API."
    result = check_grounding(answer, [_STRIPE_CHUNK])
    assert result.is_grounded is True
    assert result.overlap_score >= 0.15


def test_ungrounded_answer():
    answer = "The recipe requires flour, eggs, butter, and baking powder."
    result = check_grounding(answer, [_STRIPE_CHUNK])
    assert result.is_grounded is False
    assert result.overlap_score < 0.15


def test_empty_answer_is_ungrounded():
    result = check_grounding("", [_STRIPE_CHUNK])
    assert result == GroundingResult(is_grounded=False, overlap_score=0.0)


def test_empty_chunks_is_ungrounded():
    result = check_grounding("How do I create a PaymentIntent?", [])
    assert result == GroundingResult(is_grounded=False, overlap_score=0.0)


def test_short_answer_treated_as_grounded():
    # "OK." → "ok" is only 2 chars → filtered; no content words → grounded
    result = check_grounding("OK.", [_STRIPE_CHUNK])
    assert result == GroundingResult(is_grounded=True, overlap_score=1.0)


def test_overlap_score_is_between_0_and_1():
    result = check_grounding("Some answer about payments and refunds.", [_STRIPE_CHUNK])
    assert 0.0 <= result.overlap_score <= 1.0


def test_overlap_score_calculation():
    # chunk_words: {"create", "payment", "via", "api"} (stopwords/short removed)
    # answer_words: {"create", "payment", "now"}
    # overlap: {"create", "payment"} → 2/3 ≈ 0.667
    chunk = {"text": "create a payment via the api"}
    answer = "create payment now"
    result = check_grounding(answer, [chunk])
    assert abs(result.overlap_score - 2 / 3) < 1e-9


def test_stopwords_excluded_from_overlap():
    # answer is entirely stopwords — content words = empty → treated as grounded
    result = check_grounding("the and is to of", [_STRIPE_CHUNK])
    assert result == GroundingResult(is_grounded=True, overlap_score=1.0)


def test_ungrounded_fallback_is_string():
    assert isinstance(UNGROUNDED_FALLBACK, str)
    assert len(UNGROUNDED_FALLBACK) > 0
