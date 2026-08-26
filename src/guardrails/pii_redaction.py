"""PII redaction for user queries — regex-based, no external dependencies."""

import re
from dataclasses import dataclass, field


@dataclass
class RedactionResult:
    """Result of a PII redaction pass."""

    redacted_text: str
    replacements: list[dict] = field(default_factory=list)
    pii_detected: bool = False


# Compiled patterns applied in order: most-specific first to avoid partial overlaps.
_CARD_RE = re.compile(r"\b(?:\d[ \-]?){13,18}\d\b")
_SSN_RE = re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b")
_PHONE_RE = re.compile(
    r"(\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"
)
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)


def _luhn_check(digits: str) -> bool:
    """Return True if the digit string passes the Luhn algorithm."""
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def redact_pii(text: str) -> RedactionResult:
    """Replace PII in text with typed placeholders and return a RedactionResult."""
    if not text:
        return RedactionResult(redacted_text="", replacements=[], pii_detected=False)

    replacements: list[dict] = []

    def _make_replacer(pii_type: str, placeholder: str, luhn: bool = False):
        def replacer(match: re.Match) -> str:
            original = match.group(0)
            if luhn:
                digits = re.sub(r"\D", "", original)
                if not _luhn_check(digits):
                    return original
            replacements.append(
                {"type": pii_type, "original": original, "placeholder": placeholder}
            )
            return placeholder

        return replacer

    text = _CARD_RE.sub(_make_replacer("card", "[CARD]", luhn=True), text)
    text = _SSN_RE.sub(_make_replacer("ssn", "[SSN]"), text)
    text = _PHONE_RE.sub(_make_replacer("phone", "[PHONE]"), text)
    text = _EMAIL_RE.sub(_make_replacer("email", "[EMAIL]"), text)

    return RedactionResult(
        redacted_text=text,
        replacements=replacements,
        pii_detected=bool(replacements),
    )
