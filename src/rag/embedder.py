"""Embedder: converts text chunks into vector embeddings via Voyage AI."""

import json
import logging
import sys
import time
from pathlib import Path

import voyageai
import voyageai.error

log = logging.getLogger(__name__)

INPUT_PATH = Path("data/stripe_chunks.jsonl")
OUTPUT_PATH = Path("data/stripe_embeddings.jsonl")

MODEL = "voyage-3-lite"
DIM = 512
MAX_INPUT_TOKENS = 32_000
_RETRY_SLEEP = 1.0

# Lazy: initialized on first call to _truncate_if_needed, not at import time.
# Tests import this symbol after embed_corpus runs to verify truncation.
_ENC = None


def _get_enc():
    global _ENC
    if _ENC is None:
        import tiktoken
        _ENC = tiktoken.get_encoding("cl100k_base")
    return _ENC


class VoyageEmbedder:
    def __init__(self, client: voyageai.Client) -> None:
        self._client = client

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        for attempt in range(2):  # original + 1 retry
            if attempt > 0:
                time.sleep(_RETRY_SLEEP)
            try:
                result = self._client.embed(
                    texts, model=MODEL, input_type="document"
                )
                return result.embeddings
            except voyageai.error.AuthenticationError:
                raise
            except voyageai.error.RateLimitError:
                if attempt == 1:
                    raise
                log.warning(
                    "Rate limit hit (attempt %d), retrying in %.0fs…",
                    attempt + 1,
                    _RETRY_SLEEP,
                )
        raise RuntimeError("embed_batch: exhausted retries")  # unreachable

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string with input_type='query'."""
        result = self._client.embed([text], model=MODEL, input_type="query")
        return result.embeddings[0]


def _load_embedded_ids(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    ids: set[str] = set()
    with output_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    ids.add(json.loads(line)["chunk_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return ids


def _truncate_if_needed(text: str) -> str:
    if len(text.split()) < MAX_INPUT_TOKENS // 2:
        return text
    enc = _get_enc()
    ids = enc.encode(text)
    if len(ids) <= MAX_INPUT_TOKENS:
        return text
    log.warning(
        "Chunk exceeds %d tokens (%d); truncating.", MAX_INPUT_TOKENS, len(ids)
    )
    return enc.decode(ids[:MAX_INPUT_TOKENS])


def embed_corpus(
    input_path: Path,
    output_path: Path,
    embedder: VoyageEmbedder,
    batch_size: int = 128,
    batch_delay: float = 0.0,
    auto_confirm: bool = False,
) -> dict:
    """Read chunks JSONL, embed in batches, append to output JSONL."""
    embedded_ids = _load_embedded_ids(output_path)
    n_already = len(embedded_ids)

    # Single pass: collect unembedded, non-empty chunks.
    pending: list[dict] = []
    total_input = 0
    with input_path.open(encoding="utf-8") as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("skip malformed JSON: %s", exc)
                continue
            total_input += 1
            if chunk["chunk_id"] in embedded_ids:
                continue
            if not chunk.get("text", "").strip():
                log.warning("skip empty chunk: %s", chunk.get("chunk_id", "?"))
                continue
            pending.append(chunk)

    to_embed_count = len(pending)
    total_tokens = sum(c["token_count"] for c in pending)
    estimated_cost = total_tokens * 0.00000002

    base_stats: dict = {
        "total_chunks": total_input,
        "already_embedded": n_already,
        "newly_embedded": 0,
        "total_tokens": total_tokens,
        "estimated_cost": estimated_cost,
        "actual_cost": 0.0,
        "elapsed_s": 0.0,
        "aborted": False,
    }

    if to_embed_count == 0:
        return base_stats

    if not auto_confirm:
        print(
            f"About to embed {to_embed_count} chunks "
            f"(~{total_tokens:,} tokens). "
            f"Estimated cost: ${estimated_cost:.4f}. "
            f"Proceed? [y/N] ",
            end="",
            flush=True,
        )
        try:
            answer = input()
        except EOFError:
            answer = ""
        if answer.strip().lower() != "y":
            print("Aborted.")
            return {**base_stats, "aborted": True}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    n_batches = (to_embed_count + batch_size - 1) // batch_size
    if batch_delay > 0:
        eta_min = round(n_batches * batch_delay / 60, 1)
        print(
            f"Batch delay {batch_delay}s × {n_batches} batches"
            f" — ETA ~{eta_min} min"
        )

    t0 = time.perf_counter()
    newly_embedded = 0
    tokens_sent = 0

    with output_path.open("a", encoding="utf-8") as fout:
        for batch_num, batch_start in enumerate(
            range(0, len(pending), batch_size)
        ):
            if batch_delay > 0 and batch_num > 0:
                time.sleep(batch_delay)
            batch = pending[batch_start : batch_start + batch_size]
            texts = [_truncate_if_needed(c["text"]) for c in batch]
            vectors = embedder.embed_batch(texts)

            for chunk, vec in zip(batch, vectors):
                fout.write(
                    json.dumps(
                        {
                            "chunk_id": chunk["chunk_id"],
                            "model": MODEL,
                            "dim": DIM,
                            "embedding": vec,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            fout.flush()
            newly_embedded += len(batch)
            tokens_sent += sum(c["token_count"] for c in batch)

    elapsed = time.perf_counter() - t0
    actual_cost = tokens_sent * 0.00000002
    return {
        **base_stats,
        "newly_embedded": newly_embedded,
        "actual_cost": actual_cost,
        "elapsed_s": round(elapsed, 1),
    }


if __name__ == "__main__":
    import argparse

    from src.config import Settings

    parser = argparse.ArgumentParser(description="Embed Stripe chunks via Voyage AI.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the cost-confirmation prompt (for automation).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        metavar="N",
        help="Chunks per API request (default 128). Use 20 on Voyage free tier.",
    )
    parser.add_argument(
        "--batch-delay",
        type=float,
        default=0.0,
        metavar="S",
        help="Sleep between batches in seconds (default 0). Use 22 on free tier.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(message)s", stream=sys.stderr
    )

    settings = Settings()
    client = voyageai.Client(api_key=settings.voyage_api_key)
    emb = VoyageEmbedder(client=client)

    stats = embed_corpus(
        input_path=INPUT_PATH,
        output_path=OUTPUT_PATH,
        embedder=emb,
        batch_size=args.batch_size,
        batch_delay=args.batch_delay,
        auto_confirm=args.yes,
    )

    if stats["aborted"]:
        sys.exit(0)

    print(f"Total chunks in input : {stats['total_chunks']}")
    print(f"Already embedded      : {stats['already_embedded']}")
    print(f"Newly embedded        : {stats['newly_embedded']}")
    print(f"Tokens                : {stats['total_tokens']:,}")
    print(f"Estimated cost        : ${stats['estimated_cost']:.4f}")
    print(f"Actual cost           : ${stats['actual_cost']:.4f}")
    print(f"Elapsed               : {stats['elapsed_s']}s")
    print(f"Wrote embeddings to   : {OUTPUT_PATH}")
