"""Output safety filter — regex-based, no external dependencies."""

import re
from dataclasses import dataclass

UNSAFE_FALLBACK = (
    "I'm unable to provide that response. "
    "Please contact Stripe support directly."
)

_CATEGORIES: dict[str, re.Pattern] = {
    "profanity": re.compile(
        r"\b(fuck|shit|asshole|bastard|bitch|cunt)\b",
        re.IGNORECASE,
    ),
    "self_harm": re.compile(
        r"(kill\W+yourself|self[\W_]harm|\bsuicide\b|end\W+your\W+life)",
        re.IGNORECASE,
    ),
    "fraud_instructions": re.compile(
        r"(steal\W+card|card\W+skimming|bypass\W+fraud|launder\W+money|carding\W+tutorial)",
        re.IGNORECASE,
    ),
    "threats": re.compile(
        r"(i\W+will\W+kill|bomb\W+threat|death\W+threat)",
        re.IGNORECASE,
    ),
}


@dataclass
class SafetyResult:
    """Result of an output safety scan."""

    is_safe: bool
    reason: str | None  # matched category label; None if safe


def check_safety(text: str) -> SafetyResult:
    """Scan text for unsafe content; return SafetyResult with category if matched."""
    if not text or not text.strip():
        return SafetyResult(is_safe=True, reason=None)
    for category, pattern in _CATEGORIES.items():
        if pattern.search(text):
            return SafetyResult(is_safe=False, reason=category)
    return SafetyResult(is_safe=True, reason=None)
