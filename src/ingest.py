"""Ingest entry point: orchestrates loading, chunking, embedding, and upserting."""

import argparse
import sys
from pathlib import Path

import voyageai

from src.config import Settings
from src.rag.chunker import chunk_corpus
from src.rag.embedder import VoyageEmbedder, embed_corpus
from src.rag.loader import (
    LLMS_TXT_URL,
    fetch_all_docs,
    fetch_stripe_docs,
    parse_llms_txt,
    save_jsonl,
)
from src.rag.vectorstore import (
    CHUNKS_PATH,
    COLLECTION,
    EMBEDDINGS_PATH,
    QdrantStore,
    ingest,
)

DOCS_PATH = Path("data/stripe_docs.jsonl")

# voyage-3-lite rate: $0.02 per 1M tokens
_VOYAGE_PRICE_PER_M = 0.02
_AVG_CHUNK_TOKENS = 350


def _count_lines(path: Path) -> int:
    """Count non-empty lines in a JSONL file."""
    count = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def run_ingest(settings: Settings, recreate: bool = False) -> dict:
    """Run the full ingest pipeline and return statistics."""
    cached_steps: list[str] = []
    result: dict = {
        "docs_loaded": 0,
        "chunks_produced": 0,
        "vectors_embedded": 0,
        "vectors_skipped": 0,
        "points_upserted": 0,
        "embed_cost_usd": 0.0,
        "cached_steps": cached_steps,
    }

    # Step 1 — Load
    if DOCS_PATH.exists():
        cached_steps.append("docs")
    else:
        raw_index = fetch_stripe_docs(LLMS_TXT_URL)
        assembled = fetch_all_docs(raw_index)
        docs = parse_llms_txt(assembled)
        result["docs_loaded"] = save_jsonl(docs, DOCS_PATH)

    if not DOCS_PATH.exists():
        raise RuntimeError("docs file not found after load step")

    # Step 2 — Chunk
    if CHUNKS_PATH.exists():
        cached_steps.append("chunks")
    else:
        stats = chunk_corpus(DOCS_PATH, CHUNKS_PATH)
        result["chunks_produced"] = stats["chunks"]

    if not CHUNKS_PATH.exists():
        raise RuntimeError("chunks file not found after chunk step")

    # Step 3 — Embed (embed_corpus handles skip-if-already-embedded internally)
    embedder = VoyageEmbedder(voyageai.Client(api_key=settings.voyage_api_key))
    embed_stats = embed_corpus(
        CHUNKS_PATH, EMBEDDINGS_PATH, embedder, auto_confirm=True
    )
    result["vectors_embedded"] = embed_stats["newly_embedded"]
    result["vectors_skipped"] = embed_stats["already_embedded"]
    result["embed_cost_usd"] = embed_stats["actual_cost"]
    if embed_stats["newly_embedded"] == 0:
        cached_steps.append("embeddings")

    if not EMBEDDINGS_PATH.exists() or EMBEDDINGS_PATH.stat().st_size == 0:
        raise RuntimeError("embeddings file not found after embed step")

    # Step 4 — Upsert
    store = QdrantStore(
        url=settings.qdrant_url,
        collection=COLLECTION,
        api_key=settings.qdrant_api_key,
    )
    try:
        store.create_collection(recreate=recreate)
    except RuntimeError:
        if recreate:
            raise
        # Collection already exists — proceed to upsert on top of it

    upsert_stats = ingest(CHUNKS_PATH, EMBEDDINGS_PATH, store)
    result["points_upserted"] = upsert_stats["upserted"]

    return result


def main() -> None:
    """Run the full ingest pipeline: load → chunk → embed → upsert."""
    parser = argparse.ArgumentParser(description="Ingest Stripe docs into Qdrant")
    parser.add_argument(
        "--yes", action="store_true", help="Skip cost confirmation prompts"
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the Qdrant collection (destructive)",
    )
    args = parser.parse_args()

    settings = Settings()

    if not args.yes and not EMBEDDINGS_PATH.exists():
        if CHUNKS_PATH.exists():
            n_chunks = _count_lines(CHUNKS_PATH)
        else:
            # Rough estimate before chunks are produced
            n_chunks = 4500
        est_tokens = n_chunks * _AVG_CHUNK_TOKENS
        est_cost = (est_tokens / 1_000_000) * _VOYAGE_PRICE_PER_M
        print(
            f"Estimated embed cost: ~${est_cost:.4f} "
            f"({n_chunks} chunks, ~{est_tokens:,} tokens, voyage-3-lite)"
        )
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    try:
        result = run_ingest(settings, recreate=args.recreate)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Docs loaded : {result['docs_loaded']}")
    print(f"Chunks      : {result['chunks_produced']}")
    skipped = result["vectors_skipped"]
    print(f"Embedded    : {result['vectors_embedded']}  (skipped {skipped})")
    print(f"Upserted    : {result['points_upserted']}")
    print(f"Embed cost  : ${result['embed_cost_usd']:.4f}")
    if result["cached_steps"]:
        print(f"Cached steps: {', '.join(result['cached_steps'])}")


if __name__ == "__main__":
    main()
