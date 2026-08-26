"""Output hallucination check — word-overlap grounding, no external dependencies."""

import re
from dataclasses import dataclass

UNGROUNDED_FALLBACK = (
    "I couldn't find a reliable answer in Stripe's documentation for that question."
)

_STOPWORDS = {
    "the", "a", "an", "is", "it", "in", "of", "to", "and", "or", "for", "on",
    "at", "by", "be", "are", "was", "were", "that", "this", "with", "as",
    "from", "not", "but", "have", "has", "do", "i", "you", "we", "they", "he",
    "she", "how", "what", "which",
}

_GROUNDING_THRESHOLD = 0.15


@dataclass
class GroundingResult:
    """Result of a grounding check against retrieved chunks."""

    is_grounded: bool
    overlap_score: float  # fraction of answer content words found in chunk pool


def _content_words(text: str) -> set[str]:
    """Extract lowercase alpha tokens of ≥3 chars, excluding stopwords."""
    tokens = re.findall(r"[a-z]{3,}", text.lower())
    return {t for t in tokens if t not in _STOPWORDS}


def check_grounding(answer: str, chunks: list[dict]) -> GroundingResult:
    """Return GroundingResult comparing answer content words against chunk words."""
    if not answer:
        return GroundingResult(is_grounded=False, overlap_score=0.0)
    if not chunks:
        return GroundingResult(is_grounded=False, overlap_score=0.0)

    chunk_words: set[str] = set()
    for chunk in chunks:
        chunk_words |= _content_words(chunk.get("text", ""))

    answer_words = _content_words(answer)

    if not answer_words:
        return GroundingResult(is_grounded=True, overlap_score=1.0)

    overlap_score = len(answer_words & chunk_words) / len(answer_words)
    return GroundingResult(
        is_grounded=overlap_score >= _GROUNDING_THRESHOLD,
        overlap_score=overlap_score,
    )
