"""Prompt injection detection — pattern-based, no external dependencies."""

import re
from dataclasses import dataclass


@dataclass
class InjectionResult:
    """Result of a prompt injection detection pass."""

    is_injection: bool
    matched_pattern: str | None  # first matched pattern source string, for logging


_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\W+(all\W+)?previous\W+instructions?", re.IGNORECASE),
    re.compile(r"forget\W+(your\W+)?(previous\W+)?instructions?", re.IGNORECASE),
    re.compile(r"you\W+are\W+now\W+\w+", re.IGNORECASE),
    re.compile(
        r"act\W+as\W+(a\W+)?(?!customer|user|merchant)\w{2,}", re.IGNORECASE
    ),
    re.compile(r"pretend\W+(you\W+are|to\W+be)", re.IGNORECASE),
    re.compile(r"disregard\W+(all\W+)?previous", re.IGNORECASE),
    re.compile(r"override\W+(your\W+)?(instructions?|prompt|rules?)", re.IGNORECASE),
    re.compile(r"reveal\W+(your\W+)?(system\W+)?prompt", re.IGNORECASE),
    re.compile(r"(jailbreak|dan\b)", re.IGNORECASE),
    re.compile(r"do\W+anything\W+now", re.IGNORECASE),
]


def detect_prompt_injection(text: str) -> InjectionResult:
    """Return InjectionResult indicating whether text contains an injection attempt."""
    if not text or not text.strip():
        return InjectionResult(is_injection=False, matched_pattern=None)

    for pattern in _PATTERNS:
        if pattern.search(text):
            return InjectionResult(is_injection=True, matched_pattern=pattern.pattern)

    return InjectionResult(is_injection=False, matched_pattern=None)
