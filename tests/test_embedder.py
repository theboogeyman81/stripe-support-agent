"""Tests for src/rag/embedder.py — no network calls."""

import json
import math
from unittest.mock import MagicMock

import pytest
import voyageai.error

from src.rag.embedder import DIM, VoyageEmbedder, embed_corpus


def _mock_result(n: int, dim: int = DIM, total_tokens: int = 10):
    result = MagicMock()
    result.embeddings = [[0.1] * dim for _ in range(n)]
    result.total_tokens = total_tokens
    return result


def test_embed_batch_returns_correct_shape():
    """embed_batch returns one DIM-length vector per input text."""
    client = MagicMock()
    client.embed.return_value = _mock_result(2)
    embedder = VoyageEmbedder(client=client)

    vectors = embedder.embed_batch(["hello", "world"])

    assert len(vectors) == 2
    assert all(len(v) == DIM for v in vectors)


def test_embed_batch_uses_document_input_type():
    """embed_batch calls Voyage with input_type=document and the right model."""
    client = MagicMock()
    client.embed.return_value = _mock_result(1)
    embedder = VoyageEmbedder(client=client)

    embedder.embed_batch(["hello"])

    _, kwargs = client.embed.call_args
    assert kwargs["input_type"] == "document"
    assert kwargs["model"] == "voyage-3-lite"


def test_embed_batch_retries_then_succeeds(monkeypatch):
    """A transient error on the first attempt is retried and succeeds."""
    monkeypatch.setattr("src.rag.embedder.time.sleep", lambda _: None)
    client = MagicMock()
    client.embed.side_effect = [
        voyageai.error.RateLimitError("rate limited"),
        _mock_result(1),
    ]
    embedder = VoyageEmbedder(client=client)

    vectors = embedder.embed_batch(["hello"])

    assert len(vectors) == 1
    assert client.embed.call_count == 2


def test_embed_batch_retry_exhausted_raises(monkeypatch):
    """After the retry also fails, embed_batch raises (2 attempts total)."""
    monkeypatch.setattr("src.rag.embedder.time.sleep", lambda _: None)
    client = MagicMock()
    client.embed.side_effect = voyageai.error.RateLimitError("rate limited")
    embedder = VoyageEmbedder(client=client)

    with pytest.raises(voyageai.error.RateLimitError):
        embedder.embed_batch(["hello"])

    assert client.embed.call_count == 2


def test_embed_batch_auth_error_not_retried():
    """AuthenticationError is not retryable — it propagates immediately."""
    client = MagicMock()
    client.embed.side_effect = voyageai.error.AuthenticationError("bad key")
    embedder = VoyageEmbedder(client=client)

    with pytest.raises(voyageai.error.AuthenticationError):
        embedder.embed_batch(["hello"])

    assert client.embed.call_count == 1


def _write_chunks(path, chunk_ids):
    with path.open("w", encoding="utf-8") as f:
        for cid in chunk_ids:
            f.write(
                json.dumps(
                    {
                        "chunk_id": cid,
                        "doc_url": "https://docs.stripe.com/x.md",
                        "doc_title": "X",
                        "chunk_index": 0,
                        "text": f"text for {cid}",
                        "token_count": 5,
                    }
                )
                + "\n"
            )


def test_embed_corpus_output_schema(tmp_path):
    """Output records have exactly the required schema, no NaN/null values."""
    chunks_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "embeddings.jsonl"
    _write_chunks(chunks_path, ["a", "b", "c"])

    client = MagicMock()
    client.embed.return_value = _mock_result(3)
    embedder = VoyageEmbedder(client=client)

    embed_corpus(chunks_path, out_path, auto_confirm=True, embedder=embedder)

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    for line in lines:
        rec = json.loads(line)
        assert set(rec.keys()) == {"chunk_id", "model", "dim", "embedding"}
        assert rec["model"] == "voyage-3-lite"
        assert rec["dim"] == DIM
        assert len(rec["embedding"]) == DIM
        assert all(
            isinstance(x, (int, float)) and not math.isnan(x)
            for x in rec["embedding"]
        )


def test_embed_corpus_resume_only_embeds_missing(tmp_path):
    """A partial output file causes only the missing chunk_ids to be embedded."""
    chunks_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "embeddings.jsonl"
    _write_chunks(chunks_path, ["a", "b", "c", "d"])
    with out_path.open("w", encoding="utf-8") as f:
        for cid in ("a", "b"):
            rec = {
                "chunk_id": cid,
                "model": "voyage-3-lite",
                "dim": DIM,
                "embedding": [0.0] * DIM,
            }
            f.write(json.dumps(rec) + "\n")

    client = MagicMock()
    client.embed.return_value = _mock_result(2)
    embedder = VoyageEmbedder(client=client)

    stats = embed_corpus(chunks_path, out_path, auto_confirm=True, embedder=embedder)

    (call_texts,), _ = client.embed.call_args
    assert set(call_texts) == {"text for c", "text for d"}
    assert stats["already_embedded"] == 2
    assert stats["newly_embedded"] == 2
    assert len(out_path.read_text(encoding="utf-8").splitlines()) == 4


def test_embed_corpus_second_run_is_noop(tmp_path):
    """Re-running after a full run makes zero new embed calls."""
    chunks_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "embeddings.jsonl"
    _write_chunks(chunks_path, ["a", "b"])

    client = MagicMock()
    client.embed.return_value = _mock_result(2)
    embedder = VoyageEmbedder(client=client)

    embed_corpus(chunks_path, out_path, auto_confirm=True, embedder=embedder)
    client.embed.reset_mock()

    stats = embed_corpus(chunks_path, out_path, auto_confirm=True, embedder=embedder)

    assert client.embed.call_count == 0
    assert stats["newly_embedded"] == 0
    assert len(out_path.read_text(encoding="utf-8").splitlines()) == 2


def test_embed_corpus_aborts_on_default_no(tmp_path, monkeypatch):
    """Without --yes, a non-'y' response aborts and makes no embed calls."""
    chunks_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "embeddings.jsonl"
    _write_chunks(chunks_path, ["a"])
    monkeypatch.setattr("builtins.input", lambda: "n")

    client = MagicMock()
    embedder = VoyageEmbedder(client=client)

    stats = embed_corpus(chunks_path, out_path, auto_confirm=False, embedder=embedder)

    assert client.embed.call_count == 0
    assert stats["aborted"] is True
    assert not out_path.exists()


def test_embed_corpus_truncates_oversized_text(tmp_path, caplog):
    """Text exceeding MAX_INPUT_TOKENS is truncated and a warning is logged."""
    chunks_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "embeddings.jsonl"
    huge_text = "word " * 40_000
    with chunks_path.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "chunk_id": "big",
                    "doc_url": "u",
                    "doc_title": "t",
                    "chunk_index": 0,
                    "text": huge_text,
                    "token_count": 40_000,
                }
            )
            + "\n"
        )

    client = MagicMock()
    client.embed.return_value = _mock_result(1)
    embedder = VoyageEmbedder(client=client)

    with caplog.at_level("WARNING"):
        embed_corpus(chunks_path, out_path, auto_confirm=True, embedder=embedder)

    (call_texts,), _ = client.embed.call_args
    from src.rag.embedder import _ENC, MAX_INPUT_TOKENS

    assert len(_ENC.encode(call_texts[0])) <= MAX_INPUT_TOKENS
    assert "truncat" in caplog.text.lower()


def test_embed_corpus_skips_empty_text_chunk(tmp_path, caplog):
    """A chunk with empty/whitespace text is skipped with a warning."""
    chunks_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "embeddings.jsonl"
    with chunks_path.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "chunk_id": "valid",
                    "doc_url": "u",
                    "doc_title": "t",
                    "chunk_index": 0,
                    "text": "real content",
                    "token_count": 2,
                }
            )
            + "\n"
        )
        f.write(
            json.dumps(
                {
                    "chunk_id": "empty",
                    "doc_url": "u",
                    "doc_title": "t",
                    "chunk_index": 1,
                    "text": "   ",
                    "token_count": 0,
                }
            )
            + "\n"
        )

    client = MagicMock()
    client.embed.return_value = _mock_result(1)
    embedder = VoyageEmbedder(client=client)

    with caplog.at_level("WARNING"):
        stats = embed_corpus(
            chunks_path, out_path, auto_confirm=True, embedder=embedder
        )

    (call_texts,), _ = client.embed.call_args
    assert call_texts == ["real content"]
    assert stats["newly_embedded"] == 1
    assert len(out_path.read_text(encoding="utf-8").splitlines()) == 1


def test_embed_corpus_stats_keys(tmp_path):
    """The returned stats dict has all keys the CLI printer depends on."""
    chunks_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "embeddings.jsonl"
    _write_chunks(chunks_path, ["a"])

    client = MagicMock()
    client.embed.return_value = _mock_result(1)
    embedder = VoyageEmbedder(client=client)

    stats = embed_corpus(chunks_path, out_path, auto_confirm=True, embedder=embedder)

    for key in (
        "total_chunks",
        "already_embedded",
        "newly_embedded",
        "total_tokens",
        "estimated_cost",
        "actual_cost",
        "elapsed_s",
        "aborted",
    ):
        assert key in stats
