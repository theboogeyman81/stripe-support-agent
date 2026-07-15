"""Vectorstore: upserts and queries vectors in Qdrant."""

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

import voyageai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.config import Settings
from src.rag.embedder import VoyageEmbedder

log = logging.getLogger(__name__)

CHUNKS_PATH = Path("data/stripe_chunks.jsonl")
EMBEDDINGS_PATH = Path("data/stripe_embeddings.jsonl")
COLLECTION = "stripe_docs"
VECTOR_SIZE = 512


def _chunk_id_to_point_id(chunk_id: str) -> str:
    """Convert an arbitrary chunk_id string to a deterministic UUID."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class QdrantStore:
    def __init__(self, url: str, collection: str, api_key: str = "") -> None:
        is_local = "localhost" in url or "127.0.0.1" in url
        if not is_local and not api_key:
            raise ValueError(
                f"QDRANT_API_KEY is required when connecting to a cloud URL ({url}). "
                "Set it in your .env file."
            )
        self._collection = collection
        self._client = QdrantClient(url=url, api_key=api_key if api_key else None)

    def create_collection(self, recreate: bool = False) -> None:
        exists = self._client.collection_exists(self._collection)
        if exists and not recreate:
            raise RuntimeError(
                f"Collection '{self._collection}' already exists. "
                "Re-run with --recreate to drop and recreate it."
            )
        if exists:
            self._client.delete_collection(self._collection)
        self._client.create_collection(
            self._collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

    def upsert_batch(self, points: list[PointStruct]) -> None:
        self._client.upsert(collection_name=self._collection, points=points)

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict]:
        response = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )
        return [
            {
                "chunk_id": pt.payload["chunk_id"],
                "score": pt.score,
                "doc_url": pt.payload["doc_url"],
                "doc_title": pt.payload["doc_title"],
                "text": pt.payload["text"],
                "chunk_index": pt.payload["chunk_index"],
            }
            for pt in response.points
        ]

    def count(self) -> int:
        return self._client.count(self._collection).count


def ingest(
    chunks_path: Path,
    embeddings_path: Path,
    store: QdrantStore,
    batch_size: int = 256,
) -> dict:
    """Join chunks + embeddings by chunk_id and upsert into Qdrant."""
    # Pass 1: load all embeddings into memory keyed by chunk_id (~17 MB)
    embeddings: dict[str, list[float]] = {}
    with embeddings_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                embeddings[rec["chunk_id"]] = rec["embedding"]
            except (json.JSONDecodeError, KeyError) as exc:
                log.warning("skip malformed embedding line: %s", exc)

    # Pass 2: stream chunks, join with embeddings, upsert in batches
    batch: list[PointStruct] = []
    n_total = 0
    n_upserted = 0
    n_skipped_no_embedding = 0
    seen_chunk_ids: set[str] = set()

    with chunks_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("skip malformed chunk line: %s", exc)
                continue

            n_total += 1
            chunk_id = chunk["chunk_id"]
            seen_chunk_ids.add(chunk_id)

            if chunk_id not in embeddings:
                log.warning("no embedding for chunk_id=%s — skipping", chunk_id)
                n_skipped_no_embedding += 1
                continue

            batch.append(
                PointStruct(
                    id=_chunk_id_to_point_id(chunk_id),
                    vector=embeddings[chunk_id],
                    payload={
                        "chunk_id": chunk_id,
                        "doc_url": chunk["doc_url"],
                        "doc_title": chunk["doc_title"],
                        "chunk_index": chunk["chunk_index"],
                        "text": chunk["text"],
                        "token_count": chunk["token_count"],
                    },
                )
            )

            if len(batch) == batch_size:
                store.upsert_batch(batch)
                n_upserted += len(batch)
                batch = []

    if batch:
        store.upsert_batch(batch)
        n_upserted += len(batch)

    extra_ids = set(embeddings.keys()) - seen_chunk_ids
    for eid in extra_ids:
        log.warning("embedding has no matching chunk: chunk_id=%s", eid)

    return {
        "total_chunks": n_total,
        "total_embeddings": len(embeddings),
        "upserted": n_upserted,
        "skipped_no_embedding": n_skipped_no_embedding,
        "extra_embeddings": len(extra_ids),
    }


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Embed query and return top_k semantically similar chunks from Qdrant."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if top_k <= 0:
        raise ValueError("top_k must be > 0")

    settings = Settings()
    embedder = VoyageEmbedder(client=voyageai.Client(api_key=settings.voyage_api_key))
    query_vector = embedder.embed_query(query)
    store = QdrantStore(
        url=settings.qdrant_url,
        collection=COLLECTION,
        api_key=settings.qdrant_api_key,
    )
    return store.search(query_vector, top_k=top_k)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qdrant vectorstore CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Upsert chunks+embeddings into Qdrant")
    p_ingest.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the collection first (destructive).",
    )

    p_search = sub.add_parser("search", help="Test retrieval against Qdrant")
    p_search.add_argument("query", help="Natural language query string")
    p_search.add_argument("--top-k", type=int, default=5, metavar="N")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(message)s", stream=sys.stderr
    )

    settings = Settings()

    if args.cmd == "ingest":
        store = QdrantStore(
            url=settings.qdrant_url,
            collection=COLLECTION,
            api_key=settings.qdrant_api_key,
        )
        store.create_collection(recreate=args.recreate)
        stats = ingest(
            chunks_path=CHUNKS_PATH,
            embeddings_path=EMBEDDINGS_PATH,
            store=store,
        )
        print(f"Total chunks       : {stats['total_chunks']}")
        print(f"Total embeddings   : {stats['total_embeddings']}")
        print(f"Upserted           : {stats['upserted']}")
        print(f"Skipped (no embed) : {stats['skipped_no_embedding']}")
        print(f"Extra embeddings   : {stats['extra_embeddings']}")
        print(f"Collection         : {COLLECTION}")

    elif args.cmd == "search":
        hits = retrieve(args.query, top_k=args.top_k)
        for i, hit in enumerate(hits, 1):
            print(f"\n--- Hit {i} (score={hit['score']:.4f}) ---")
            print(f"URL   : {hit['doc_url']}")
            print(f"Title : {hit['doc_title']}")
            snippet = hit["text"][:300] + ("..." if len(hit["text"]) > 300 else "")
            print(f"Text  : {snippet}")
