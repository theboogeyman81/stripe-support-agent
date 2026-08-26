"""Off-topic query classification — keyword-based, no external dependencies."""

import re
from dataclasses import dataclass


@dataclass
class OffTopicResult:
    """Result of an off-topic classification pass."""

    is_off_topic: bool
    reason: str | None  # matched domain label for logging; None if not off-topic


# Gate 1: any match here means the query is Stripe/payment-related → pass through.
_STRIPE_TERMS = re.compile(
    r"\b(stripe|payment|paymentintent|charge|refund|invoice|subscription|"
    r"webhook|checkout|connect|radar|billing|payout|dispute|card|bank|"
    r"transfer|customer|product|price|coupon|promo|api|sdk|dashboard|"
    r"account|merchant|fraud|3ds|authentication|mandate|tax|issuing|"
    r"terminal|identity)\b",
    re.IGNORECASE,
)

# Gate 2: a match here (only reached when gate 1 fails) signals an off-topic domain.
_DOMAINS: dict[str, re.Pattern] = {
    "cooking": re.compile(
        r"\b(recipe|ingredient|bake|cook|cuisine|dish|meal|oven|roast|simmer)\b",
        re.IGNORECASE,
    ),
    "sports": re.compile(
        r"\b(football|basketball|soccer|nfl|nba|score|touchdown|match|league|playoffs)\b",
        re.IGNORECASE,
    ),
    "weather": re.compile(
        r"\b(weather|forecast|temperature|humidity|rain|snow|sunny|cloudy|wind)\b",
        re.IGNORECASE,
    ),
    "entertainment": re.compile(
        r"\b(movie|film|actor|singer|song|album|celebrity|lyrics|trailer|episode)\b",
        re.IGNORECASE,
    ),
    "health": re.compile(
        r"\b(symptoms?|diagnosis|medicine|doctor|hospital|prescription|therapy|disease)\b",
        re.IGNORECASE,
    ),
}


def classify_topic(text: str) -> OffTopicResult:
    """Return OffTopicResult indicating whether text is clearly off-topic for Stripe."""
    if not text or not text.strip():
        return OffTopicResult(is_off_topic=False, reason=None)

    if _STRIPE_TERMS.search(text):
        return OffTopicResult(is_off_topic=False, reason=None)

    for domain, pattern in _DOMAINS.items():
        if pattern.search(text):
            return OffTopicResult(is_off_topic=True, reason=domain)

    return OffTopicResult(is_off_topic=False, reason=None)
