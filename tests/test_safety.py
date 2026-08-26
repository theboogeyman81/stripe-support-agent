"""Tests for src/guardrails/safety.py — pure unit tests, no network calls."""

from src.guardrails.safety import UNSAFE_FALLBACK, SafetyResult, check_safety


def test_profanity_detected():
    result = check_safety("What the fuck is going on with my payment?")
    assert result.is_safe is False
    assert result.reason == "profanity"


def test_self_harm_kill_yourself():
    result = check_safety("You should kill yourself.")
    assert result.is_safe is False
    assert result.reason == "self_harm"


def test_self_harm_suicide():
    result = check_safety("This mentions suicide risks.")
    assert result.is_safe is False
    assert result.reason == "self_harm"


def test_self_harm_end_your_life():
    result = check_safety("end your life now")
    assert result.is_safe is False
    assert result.reason == "self_harm"


def test_fraud_instructions_bypass_fraud():
    result = check_safety("Here is how to bypass fraud detection.")
    assert result.is_safe is False
    assert result.reason == "fraud_instructions"


def test_card_skimming_detected():
    result = check_safety("This is a card skimming tutorial.")
    assert result.is_safe is False
    assert result.reason == "fraud_instructions"


def test_threat_detected():
    result = check_safety("I will kill you if you don't pay.")
    assert result.is_safe is False
    assert result.reason == "threats"


def test_normal_stripe_answer_is_safe():
    result = check_safety(
        "To create a PaymentIntent, call the API with amount and currency."
    )
    assert result.is_safe is True
    assert result.reason is None


def test_empty_answer_is_safe():
    result = check_safety("")
    assert result == SafetyResult(is_safe=True, reason=None)


def test_reason_is_none_when_safe():
    result = check_safety("Stripe supports many payment methods.")
    assert result.reason is None


def test_case_insensitive_detection():
    result = check_safety("KILL YOURSELF NOW")
    assert result.is_safe is False
    assert result.reason == "self_harm"


def test_unsafe_fallback_is_string():
    assert isinstance(UNSAFE_FALLBACK, str)
    assert len(UNSAFE_FALLBACK) > 0
