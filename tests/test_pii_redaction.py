"""Tests for src/guardrails/pii_redaction.py — pure unit tests, no network calls."""

from src.guardrails.pii_redaction import RedactionResult, redact_pii


def test_email_is_redacted():
    result = redact_pii("email me at foo@bar.com")
    assert "[EMAIL]" in result.redacted_text
    assert "foo@bar.com" not in result.redacted_text
    assert result.pii_detected is True


def test_phone_us_format_is_redacted():
    result = redact_pii("call 555-867-5309")
    assert "[PHONE]" in result.redacted_text
    assert "555-867-5309" not in result.redacted_text
    assert result.pii_detected is True


def test_phone_e164_is_redacted():
    result = redact_pii("my number is +14155552671")
    assert "[PHONE]" in result.redacted_text
    assert "4155552671" not in result.redacted_text
    assert result.pii_detected is True


def test_card_valid_luhn_is_redacted():
    # 4242 4242 4242 4242 is the canonical Stripe test card (passes Luhn)
    result = redact_pii("my card is 4242 4242 4242 4242 please charge it")
    assert "[CARD]" in result.redacted_text
    assert "4242" not in result.redacted_text
    assert result.pii_detected is True


def test_card_invalid_luhn_not_redacted():
    # 1234 5678 9012 3456 fails Luhn — should not be redacted
    result = redact_pii("number 1234 5678 9012 3456")
    assert "[CARD]" not in result.redacted_text
    assert result.pii_detected is False


def test_ssn_is_redacted():
    result = redact_pii("SSN: 123-45-6789")
    assert "[SSN]" in result.redacted_text
    assert "123-45-6789" not in result.redacted_text
    assert result.pii_detected is True


def test_multiple_pii_all_redacted():
    text = "card 4242 4242 4242 4242 and email foo@bar.com"
    result = redact_pii(text)
    assert "[CARD]" in result.redacted_text
    assert "[EMAIL]" in result.redacted_text
    assert "4242" not in result.redacted_text
    assert "foo@bar.com" not in result.redacted_text
    assert len(result.replacements) == 2


def test_clean_text_unchanged():
    text = "How do I create a PaymentIntent?"
    result = redact_pii(text)
    assert result.redacted_text == text
    assert result.pii_detected is False
    assert result.replacements == []


def test_empty_string_returns_empty():
    result = redact_pii("")
    assert result == RedactionResult(
        redacted_text="", replacements=[], pii_detected=False
    )


def test_replacements_list_has_correct_type():
    result = redact_pii("reach me at test@example.com")
    assert len(result.replacements) == 1
    assert result.replacements[0]["type"] == "email"
    assert result.replacements[0]["placeholder"] == "[EMAIL]"
    assert result.replacements[0]["original"] == "test@example.com"


def test_stripe_test_key_not_matched_as_card():
    # API keys are alphanumeric — the card regex matches only digit sequences
    result = redact_pii("key: sk_test_4eC39HqLyjWDarjtT7")
    assert "[CARD]" not in result.redacted_text
    assert result.pii_detected is False
