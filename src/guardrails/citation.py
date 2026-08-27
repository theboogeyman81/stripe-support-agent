"""Output citation enforcement — structural check that sources list is non-empty."""

import re

_STOPWORDS = {
    "the", "a", "an", "is", "it", "in", "of", "to", "and", "or", "for", "on",
    "at", "by", "be", "are", "was", "were", "that", "this", "with", "as",
    "from", "not", "but", "have", "has", "do", "i", "you", "we", "they", "he",
    "she", "how", "what", "which",
}


def _content_words(text: str) -> set[str]:
    """Extract lowercase alpha tokens of ≥3 chars, excluding stopwords."""
    tokens = re.findall(r"[a-z]{3,}", text.lower())
    return {t for t in tokens if t not in _STOPWORDS}


def enforce_citation(answer: str, sources: list) -> bool:
    """Return False if sources is empty and answer has real content words."""
    if sources:
        return True
    if not _content_words(answer):
        return True
    return False
