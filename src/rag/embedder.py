"""Embedder: converts text chunks into vector embeddings via Voyage AI."""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import tiktoken
import voyageai
import voyageai.error

from src.config import Settings

log = logging.getLogger(__name__)

_ENC = tiktoken.get_encoding("cl100k_base")
MODEL = "voyage-3-lite"
DIM = 512
MAX_INPUT_TOKENS = 32_000
COST_PER_TOKEN = 0.00000002  # voyage-3-lite: $0.02 / 1M tokens

INPUT_PATH = Path("data/stripe_chunks.jsonl")
OUTPUT_PATH = Path("data/stripe_embeddings.jsonl")

# No shared "transient" base class in voyageai.error, so the retryable set
# must be an explicit tuple. AuthenticationError / InvalidRequestError /
# MalformedRequestError are deliberately excluded — retrying can't fix those.
_RETRYABLE = (
    voyageai.error.RateLimitError,
    voyageai.error.ServerError,
    voyageai.error.ServiceUnavailableError,
    voyageai.error.APIConnectionError,
    voyageai.error.TryAgain,
)


class VoyageEmbedder:
    """Wraps the Voyage client with retry-on-transient-error semantics."""

    def __init__(
        self, client: voyageai.Client | None = None, model: str = MODEL
    ) -> None:
        if client is not None:
            self.client = client
        else:
            settings = Settings()
            self.client = voyageai.Client(api_key=settings.voyage_api_key)
        self.model = model
        self.last_total_tokens = 0

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, retrying once on a transient error."""
        for attempt in range(2):
            try:
                result = self.client.embed(
                    texts, model=self.model, input_type="document"
                )
                self.last_total_tokens = result.total_tokens
                return result.embeddings
            except _RETRYABLE as exc:
                if attempt == 1:
                    log.error("embed_batch failed after retry: %s", exc)
                    raise
                log.warning("transient Voyage error (%s) — retrying in 1s", exc)
                time.sleep(1)
        raise AssertionError("unreachable")


def _load_done_ids(output_path: Path) -> set[str]:
    """Return the set of chunk_ids already present in the output file."""
    done: set[str] = set()
    if not output_path.exists():
        return done
    with output_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning(
                    "skip malformed JSON line in existing output file: %s", exc
                )
                continue
            if cid := rec.get("chunk_id"):
                done.add(cid)
    return done


def _prompt_confirm() -> bool:
    """Read a y/N confirmation from stdin. Default is No."""
    ans = input().strip().lower()
    return ans in ("y", "yes")


def embed_corpus(
    input_path: Path,
    output_path: Path,
    batch_size: int = 128,
    auto_confirm: bool = False,
    embedder: VoyageEmbedder | None = None,
) -> dict:
    """Embed every unembedded chunk in input_path, appending to output_path."""
    done_ids = _load_done_ids(output_path)
    already_embedded = 0
    pending: list[tuple[str, str, int]] = []

    with input_path.open(encoding="utf-8") as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("skip malformed JSON line: %s", exc)
                continue

            chunk_id = chunk.get("chunk_id")
            if chunk_id in done_ids:
                already_embedded += 1
                continue

            text = chunk.get("text", "").strip()
            if not text:
                log.warning("skip empty text for chunk_id=%s", chunk_id)
                continue

            token_ids = _ENC.encode(text)
            if len(token_ids) > MAX_INPUT_TOKENS:
                log.warning(
                    "truncating chunk_id=%s from %d to %d tokens",
                    chunk_id,
                    len(token_ids),
                    MAX_INPUT_TOKENS,
                )
                text = _ENC.decode(token_ids[:MAX_INPUT_TOKENS])
                token_count = MAX_INPUT_TOKENS
            else:
                token_count = len(token_ids)

            pending.append((chunk_id, text, token_count))

    total_chunks = already_embedded + len(pending)

    if not pending:
        print("Nothing to embed — all chunks already have embeddings.")
        return {
            "total_chunks": total_chunks,
            "already_embedded": already_embedded,
            "newly_embedded": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0,
            "actual_cost": 0.0,
            "elapsed_s": 0.0,
            "aborted": False,
        }

    total_tokens = sum(t for _, _, t in pending)
    estimated_cost = total_tokens * COST_PER_TOKEN

    print(
        f"About to embed {len(pending)} chunks (~{total_tokens} tokens). "
        f"Estimated cost: ${estimated_cost:.4f}. Proceed? [y/N] ",
        end="",
    )
    if not auto_confirm:
        if not _prompt_confirm():
            print("Aborted.")
            return {
                "total_chunks": total_chunks,
                "already_embedded": already_embedded,
                "newly_embedded": 0,
                "total_tokens": 0,
                "estimated_cost": estimated_cost,
                "actual_cost": 0.0,
                "elapsed_s": 0.0,
                "aborted": True,
            }
    else:
        print("(auto-confirmed via --yes)")

    if embedder is None:
        embedder = VoyageEmbedder()

    t0 = time.perf_counter()
    newly_embedded = 0
    actual_tokens = 0
    batch_count = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as fout:
        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            texts = [text for _, text, _ in batch]
            vectors = embedder.embed_batch(texts)
            actual_tokens += embedder.last_total_tokens
            batch_count += 1

            for (chunk_id, _, _), embedding in zip(batch, vectors, strict=True):
                rec = {
                    "chunk_id": chunk_id,
                    "model": embedder.model,
                    "dim": DIM,
                    "embedding": embedding,
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                newly_embedded += 1
            fout.flush()

    elapsed = time.perf_counter() - t0
    return {
        "total_chunks": total_chunks,
        "already_embedded": already_embedded,
        "newly_embedded": newly_embedded,
        "total_tokens": actual_tokens,
        "estimated_cost": estimated_cost,
        "actual_cost": actual_tokens * COST_PER_TOKEN,
        "elapsed_s": round(elapsed, 1),
        "avg_ms_per_batch": (
            round(elapsed / batch_count * 1000, 1) if batch_count else 0.0
        ),
        "aborted": False,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(message)s", stream=sys.stderr
    )
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--yes", action="store_true", help="skip the cost confirmation prompt"
    )
    args = parser.parse_args()

    stats = embed_corpus(INPUT_PATH, OUTPUT_PATH, auto_confirm=args.yes)
    print(f"Total chunks    : {stats['total_chunks']}")
    print(f"Already embedded: {stats['already_embedded']}")
    print(f"Newly embedded  : {stats['newly_embedded']}")
    print(f"Total tokens    : {stats['total_tokens']}")
    print(f"Estimated cost  : ${stats['estimated_cost']:.4f}")
    print(f"Actual cost     : ${stats['actual_cost']:.4f}")
    print(f"Elapsed         : {stats['elapsed_s']}s")
    print(f"Wrote embeddings to {OUTPUT_PATH}")
