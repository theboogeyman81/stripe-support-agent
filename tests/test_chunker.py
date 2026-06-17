"""Tests for src/rag/chunker.py — no network calls, no corpus file I/O."""

import tiktoken
import pytest

from src.rag.chunker import count_tokens, chunk_text, chunk_doc

_ENC = tiktoken.get_encoding("cl100k_base")

# ~10 tokens per repetition
SENTENCE = "The quick brown fox jumps over the lazy dog. "


def test_count_tokens_known_string():
    """count_tokens returns a sensible integer for a known short string."""
    n = count_tokens("Hello, world!")
    assert isinstance(n, int)
    assert 2 <= n <= 8


def test_chunk_text_short_returns_one_chunk():
    """A string well under 500 tokens produces exactly one chunk."""
    short = "This is a short sentence about Stripe payments."
    chunks = chunk_text(short)
    assert len(chunks) == 1
    assert "short sentence" in chunks[0]


def test_chunk_text_long_returns_multiple_chunks():
    """~1500-token input produces ≥ 3 chunks, each within the token limit."""
    long_text = SENTENCE * 150
    chunks = chunk_text(long_text, target_tokens=500, overlap_tokens=50)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert count_tokens(chunk) <= 550


def test_chunk_text_overlap_content_appears_in_previous_chunk():
    """Text at the start of chunk N+1 also appears near the end of chunk N.

    We verify the semantic overlap property at the string level. Testing at the
    token-ID level is unreliable because .strip() on the decoded chunk shifts
    the token boundary, making re-encoded ids[-50:] inconsistent with the
    implementation's internal cur_ids[-50:].
    """
    long_text = SENTENCE * 200
    chunks = chunk_text(long_text, target_tokens=500, overlap_tokens=50)
    assert len(chunks) >= 2

    # The first 50 characters of chunk 1 must appear somewhere inside chunk 0.
    start_of_chunk1 = chunks[1][:50].strip()
    assert start_of_chunk1 in chunks[0], (
        f"Start of chunk[1] not found in chunk[0].\n"
        f"chunk[1][:50]: {start_of_chunk1!r}\n"
        f"chunk[0][-100:]: {chunks[0][-100:]!r}"
    )


def test_chunk_doc_fields_and_index_sequence():
    """chunk_doc yields records with all required fields in correct index order."""
    doc = {
        "url": "https://docs.stripe.com/test.md",
        "title": "Test Doc",
        "content": SENTENCE * 200,
    }
    chunks = list(chunk_doc(doc))
    assert len(chunks) >= 2

    for i, chunk in enumerate(chunks):
        assert chunk["chunk_id"].startswith("stripe-")
        assert chunk["chunk_id"].endswith(f"-{i}")
        assert chunk["doc_url"] == "https://docs.stripe.com/test.md"
        assert chunk["doc_title"] == "Test Doc"
        assert chunk["chunk_index"] == i
        assert chunk["text"] and chunk["text"].strip()
        assert isinstance(chunk["token_count"], int) and chunk["token_count"] > 0


def test_chunk_doc_unique_ids():
    """All chunk_ids produced for a single doc are distinct."""
    doc = {
        "url": "https://docs.stripe.com/test.md",
        "title": "Test Doc",
        "content": SENTENCE * 200,
    }
    ids = [c["chunk_id"] for c in chunk_doc(doc)]
    assert len(ids) == len(set(ids))


def test_code_block_not_split():
    """A code block > 500 tokens is never split across chunks (no dangling fences)."""
    # ~17 tokens per line × 40 lines ≈ 680 tokens — clearly above the 500-token limit
    code_line = "result = some_function(argument_one, argument_two, argument_three)  # x\n"
    code_block = "```python\n" + code_line * 40 + "```"
    text = "Prose before the code block.\n\n" + code_block + "\n\nProse after the code block."

    chunks = chunk_text(text)

    for chunk in chunks:
        fence_count = chunk.count("```")
        assert fence_count % 2 == 0, (
            f"Code block split: {fence_count} fence markers in chunk:\n{chunk[:200]}"
        )
