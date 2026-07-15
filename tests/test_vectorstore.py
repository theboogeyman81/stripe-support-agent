"""Tests for src/rag/vectorstore.py — no network calls."""

import json
import uuid
from unittest.mock import MagicMock, call

import pytest

from src.rag.vectorstore import (
    COLLECTION,
    VECTOR_SIZE,
    QdrantStore,
    _chunk_id_to_point_id,
    ingest,
    retrieve,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_chunk(chunk_id: str, **overrides) -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_url": f"https://docs.stripe.com/{chunk_id}.md",
        "doc_title": f"Title {chunk_id}",
        "chunk_index": 0,
        "text": f"text for {chunk_id}",
        "token_count": 10,
        **overrides,
    }


def _fake_embedding(chunk_id: str, dim: int = VECTOR_SIZE) -> dict:
    return {
        "chunk_id": chunk_id,
        "model": "voyage-3-lite",
        "dim": dim,
        "embedding": [0.1] * dim,
    }


def _write_chunks(path, chunk_ids):
    with path.open("w", encoding="utf-8") as f:
        for cid in chunk_ids:
            f.write(json.dumps(_fake_chunk(cid)) + "\n")


def _write_embeddings(path, chunk_ids):
    with path.open("w", encoding="utf-8") as f:
        for cid in chunk_ids:
            f.write(json.dumps(_fake_embedding(cid)) + "\n")


def _make_store(mock_client=None) -> QdrantStore:
    """Build a QdrantStore with a pre-injected mock client."""
    store = QdrantStore.__new__(QdrantStore)
    store._collection = COLLECTION
    store._client = mock_client or MagicMock()
    return store


# ---------------------------------------------------------------------------
# _chunk_id_to_point_id
# ---------------------------------------------------------------------------

def test_chunk_id_to_point_id_is_deterministic():
    a = _chunk_id_to_point_id("stripe-abc-0")
    b = _chunk_id_to_point_id("stripe-abc-0")
    assert a == b


def test_chunk_id_to_point_id_is_valid_uuid():
    result = _chunk_id_to_point_id("stripe-abc-0")
    parsed = uuid.UUID(result)
    assert parsed.version == 5


def test_chunk_id_to_point_id_different_ids_differ():
    assert _chunk_id_to_point_id("a") != _chunk_id_to_point_id("b")


# ---------------------------------------------------------------------------
# QdrantStore.__init__
# ---------------------------------------------------------------------------

def test_cloud_url_without_api_key_raises():
    with pytest.raises(ValueError, match="QDRANT_API_KEY"):
        QdrantStore(
            url="https://c4810ac7.eu-west-2-0.aws.cloud.qdrant.io",
            collection=COLLECTION,
            api_key="",
        )


def test_localhost_without_api_key_is_ok(monkeypatch):
    monkeypatch.setattr("src.rag.vectorstore.QdrantClient", MagicMock())
    store = QdrantStore(url="http://localhost:6333", collection=COLLECTION, api_key="")
    assert store._collection == COLLECTION


# ---------------------------------------------------------------------------
# QdrantStore.create_collection
# ---------------------------------------------------------------------------

def test_create_collection_raises_if_exists_without_recreate():
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True
    store = _make_store(mock_client)

    with pytest.raises(RuntimeError, match="--recreate"):
        store.create_collection(recreate=False)

    mock_client.create_collection.assert_not_called()


def test_create_collection_deletes_then_recreates_when_recreate():
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True
    store = _make_store(mock_client)

    store.create_collection(recreate=True)

    mock_client.delete_collection.assert_called_once_with(COLLECTION)
    mock_client.create_collection.assert_called_once()


def test_create_collection_creates_when_not_exists():
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = False
    store = _make_store(mock_client)

    store.create_collection()

    mock_client.delete_collection.assert_not_called()
    mock_client.create_collection.assert_called_once()


# ---------------------------------------------------------------------------
# ingest — join logic
# ---------------------------------------------------------------------------

def test_ingest_correct_join(tmp_path):
    chunks_path = tmp_path / "chunks.jsonl"
    embeddings_path = tmp_path / "embeddings.jsonl"
    ids = ["a", "b", "c"]
    _write_chunks(chunks_path, ids)
    _write_embeddings(embeddings_path, ids)

    mock_client = MagicMock()
    store = _make_store(mock_client)

    stats = ingest(chunks_path, embeddings_path, store)

    assert stats["upserted"] == 3
    assert stats["skipped_no_embedding"] == 0
    assert stats["extra_embeddings"] == 0

    # Collect all PointStructs passed to upsert_batch
    all_points = [
        pt
        for c in mock_client.upsert.call_args_list
        for pt in c.kwargs.get("points", c.args[1] if len(c.args) > 1 else [])
    ]
    assert len(all_points) == 3
    payloads = {pt.payload["chunk_id"] for pt in all_points}
    assert payloads == {"a", "b", "c"}


def test_ingest_skips_chunk_with_missing_embedding(tmp_path, caplog):
    chunks_path = tmp_path / "chunks.jsonl"
    embeddings_path = tmp_path / "embeddings.jsonl"
    _write_chunks(chunks_path, ["a", "b"])
    _write_embeddings(embeddings_path, ["a"])  # "b" has no embedding

    mock_client = MagicMock()
    store = _make_store(mock_client)

    with caplog.at_level("WARNING"):
        stats = ingest(chunks_path, embeddings_path, store)

    assert stats["upserted"] == 1
    assert stats["skipped_no_embedding"] == 1
    assert "b" in caplog.text


def test_ingest_reports_extra_embeddings(tmp_path, caplog):
    chunks_path = tmp_path / "chunks.jsonl"
    embeddings_path = tmp_path / "embeddings.jsonl"
    _write_chunks(chunks_path, ["a"])
    _write_embeddings(embeddings_path, ["a", "orphan"])  # "orphan" has no chunk

    mock_client = MagicMock()
    store = _make_store(mock_client)

    with caplog.at_level("WARNING"):
        stats = ingest(chunks_path, embeddings_path, store)

    assert stats["upserted"] == 1
    assert stats["extra_embeddings"] == 1
    assert "orphan" in caplog.text


def test_ingest_stats_keys(tmp_path):
    chunks_path = tmp_path / "chunks.jsonl"
    embeddings_path = tmp_path / "embeddings.jsonl"
    _write_chunks(chunks_path, ["a"])
    _write_embeddings(embeddings_path, ["a"])

    store = _make_store()
    stats = ingest(chunks_path, embeddings_path, store)

    for key in ("total_chunks", "total_embeddings", "upserted",
                "skipped_no_embedding", "extra_embeddings"):
        assert key in stats


def test_ingest_batches_correctly(tmp_path):
    """With batch_size=2 and 5 chunks, upsert should be called 3 times."""
    chunks_path = tmp_path / "chunks.jsonl"
    embeddings_path = tmp_path / "embeddings.jsonl"
    ids = ["a", "b", "c", "d", "e"]
    _write_chunks(chunks_path, ids)
    _write_embeddings(embeddings_path, ids)

    mock_client = MagicMock()
    store = _make_store(mock_client)

    ingest(chunks_path, embeddings_path, store, batch_size=2)

    assert mock_client.upsert.call_count == 3


def test_ingest_point_id_is_deterministic_uuid(tmp_path):
    chunks_path = tmp_path / "chunks.jsonl"
    embeddings_path = tmp_path / "embeddings.jsonl"
    _write_chunks(chunks_path, ["x"])
    _write_embeddings(embeddings_path, ["x"])

    mock_client = MagicMock()
    store = _make_store(mock_client)
    ingest(chunks_path, embeddings_path, store)

    _, kwargs = mock_client.upsert.call_args
    points = kwargs["points"]
    assert len(points) == 1
    uuid.UUID(points[0].id)  # raises if not a valid UUID
    assert points[0].payload["chunk_id"] == "x"


# ---------------------------------------------------------------------------
# QdrantStore.search
# ---------------------------------------------------------------------------

def _make_scored_point(chunk_id: str, score: float = 0.9) -> MagicMock:
    pt = MagicMock()
    pt.score = score
    pt.payload = {
        "chunk_id": chunk_id,
        "doc_url": f"https://docs.stripe.com/{chunk_id}.md",
        "doc_title": f"Title {chunk_id}",
        "text": f"text for {chunk_id}",
        "chunk_index": 0,
    }
    return pt


def test_search_returns_correct_shape():
    mock_client = MagicMock()
    mock_client.query_points.return_value = MagicMock(
        points=[_make_scored_point("a", 0.95), _make_scored_point("b", 0.80)]
    )
    store = _make_store(mock_client)

    hits = store.search([0.1] * VECTOR_SIZE, top_k=2)

    assert len(hits) == 2
    assert hits[0]["chunk_id"] == "a"
    assert hits[0]["score"] == pytest.approx(0.95)
    for key in ("chunk_id", "score", "doc_url", "doc_title", "text", "chunk_index"):
        assert key in hits[0]


def test_search_passes_limit_to_client():
    mock_client = MagicMock()
    mock_client.query_points.return_value = MagicMock(points=[])
    store = _make_store(mock_client)

    store.search([0.1] * VECTOR_SIZE, top_k=7)

    _, kwargs = mock_client.query_points.call_args
    assert kwargs.get("limit") == 7


# ---------------------------------------------------------------------------
# retrieve()
# ---------------------------------------------------------------------------

def test_retrieve_empty_query_raises():
    with pytest.raises(ValueError, match="empty"):
        retrieve("   ")


def test_retrieve_zero_top_k_raises():
    with pytest.raises(ValueError, match="top_k"):
        retrieve("hello", top_k=0)


def test_retrieve_uses_query_input_type(monkeypatch):
    """retrieve() must call embed_query (input_type='query'), not embed_batch."""
    mock_voyage_client = MagicMock()
    mock_voyage_client.embed.return_value = MagicMock(
        embeddings=[[0.1] * VECTOR_SIZE]
    )

    mock_qdrant_client = MagicMock()
    mock_qdrant_client.collection_exists.return_value = True
    mock_qdrant_client.query_points.return_value = MagicMock(points=[])

    monkeypatch.setattr("src.rag.vectorstore.voyageai.Client", lambda **_: mock_voyage_client)
    monkeypatch.setattr("src.rag.vectorstore.QdrantClient", lambda **_: mock_qdrant_client)
    monkeypatch.setattr(
        "src.rag.vectorstore.Settings",
        lambda: MagicMock(
            voyage_api_key="vk",
            qdrant_url="http://localhost:6333",
            qdrant_api_key="",
        ),
    )

    retrieve("how do I refund?")

    mock_voyage_client.embed.assert_called_once()
    _, kwargs = mock_voyage_client.embed.call_args
    assert kwargs["input_type"] == "query"
