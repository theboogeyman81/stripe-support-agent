"""Tests for src/guardrails/off_topic.py — pure unit tests, no network calls."""

from src.guardrails.off_topic import OffTopicResult, classify_topic


def test_cooking_query_rejected():
    result = classify_topic("What is the best recipe for chocolate cake?")
    assert result.is_off_topic is True
    assert result.reason == "cooking"


def test_sports_query_rejected():
    result = classify_topic("Who won the NFL touchdown record?")
    assert result.is_off_topic is True
    assert result.reason == "sports"


def test_weather_query_rejected():
    result = classify_topic("What is the weather forecast for tomorrow?")
    assert result.is_off_topic is True
    assert result.reason == "weather"


def test_entertainment_query_rejected():
    result = classify_topic("Who is the best actor in that new movie?")
    assert result.is_off_topic is True
    assert result.reason == "entertainment"


def test_health_query_rejected():
    result = classify_topic("What are the symptoms of a cold?")
    assert result.is_off_topic is True
    assert result.reason == "health"


def test_stripe_payment_query_allowed():
    result = classify_topic("How do I handle a failed payment?")
    assert result.is_off_topic is False


def test_stripe_webhook_allowed():
    result = classify_topic("What is a webhook?")
    assert result.is_off_topic is False


def test_stripe_api_allowed():
    result = classify_topic("How do I use the Stripe API?")
    assert result.is_off_topic is False


def test_ambiguous_query_allowed():
    result = classify_topic("How do I get started?")
    assert result.is_off_topic is False


def test_off_topic_with_stripe_term_allowed():
    result = classify_topic(
        "What is the price of a Big Mac and how does Stripe work?"
    )
    assert result.is_off_topic is False


def test_empty_string_allowed():
    result = classify_topic("")
    assert result == OffTopicResult(is_off_topic=False, reason=None)


def test_reason_field_populated():
    result = classify_topic("What is the best recipe for pasta?")
    assert result.reason == "cooking"
