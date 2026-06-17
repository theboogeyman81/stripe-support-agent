"""Chunker: splits raw document text into overlapping token-bounded chunks."""

import hashlib
import json
import logging
import re
import statistics
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import tiktoken

log = logging.getLogger(__name__)

_ENC = tiktoken.get_encoding("cl100k_base")
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]
_CODE_FENCE_RE = re.compile(r"(```[\s\S]*?```)")

INPUT_PATH = Path("data/stripe_docs.jsonl")
OUTPUT_PATH = Path("data/stripe_chunks.jsonl")


def count_tokens(text: str) -> int:
    """Return the number of cl100k_base tokens in text."""
    return len(_ENC.encode(text))


def _segments(text: str) -> list[tuple[bool, str]]:
    """Split text into (is_code_block, segment) pairs, preserving order."""
    parts = _CODE_FENCE_RE.split(text)
    result = []
    for i, part in enumerate(parts):
        if part:
            result.append((i % 2 == 1, part))
    return result


def _split_prose(text: str, target: int, _seps: list[str] | None = None) -> list[str]:
    """Recursively split prose into atoms each ≤ target tokens."""
    if _seps is None:
        _seps = _SEPARATORS
    if count_tokens(text) <= target:
        return [text] if text.strip() else []
    for i, sep in enumerate(_seps):
        if sep == "":
            return [text]
        if sep not in text:
            continue
        raw_pieces = text.split(sep)
        atoms: list[str] = []
        for j, piece in enumerate(raw_pieces):
            rejoined = (piece + sep) if j < len(raw_pieces) - 1 else piece
            # Pass only the remaining separators so a re-attached suffix (e.g.
            # "para\n\n") cannot match the same separator and recurse infinitely.
            atoms.extend(_split_prose(rejoined, target, _seps[i + 1 :]))
        return atoms
    return [text]


def chunk_text(
    text: str,
    target_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[str]:
    """Split text into overlapping chunks of ~target_tokens, respecting code blocks."""
    atoms: list[tuple[bool, str]] = []
    for is_code, seg in _segments(text):
        if is_code:
            atoms.append((True, seg))
        else:
            for atom in _split_prose(seg, target_tokens):
                atoms.append((False, atom))

    cur_ids: list[int] = []
    chunks: list[str] = []

    for is_code, atom in atoms:
        atom_ids = _ENC.encode(atom)

        if is_code and len(atom_ids) > target_tokens:
            if cur_ids:
                chunks.append(_ENC.decode(cur_ids))
                cur_ids = []
            chunks.append(atom)
            continue

        if cur_ids and len(cur_ids) + len(atom_ids) > target_tokens:
            chunks.append(_ENC.decode(cur_ids))
            # Decode the overlap to a string first so BPE merges are consistent
            # across the junction when the new buffer is re-encoded as one unit.
            overlap_text = _ENC.decode(cur_ids[-overlap_tokens:])
            cur_ids = _ENC.encode(overlap_text + atom)
        else:
            cur_ids.extend(atom_ids)

    if cur_ids:
        chunks.append(_ENC.decode(cur_ids))

    return [c.strip() for c in chunks if c.strip()]


def chunk_doc(doc: dict) -> Iterator[dict]:
    """Yield chunk records for a single doc dict."""
    url = doc.get("url", "")
    title = doc.get("title", "")
    content = doc.get("content", "").strip()

    if not content:
        log.warning("chunk_doc: empty content for %s — skipped", url)
        return

    url_hash = hashlib.sha1(url.encode()).hexdigest()[:8]
    for i, text in enumerate(chunk_text(content)):
        yield {
            "chunk_id": f"stripe-{url_hash}-{i}",
            "doc_url": url,
            "doc_title": title,
            "chunk_index": i,
            "text": text,
            "token_count": count_tokens(text),
        }


def chunk_corpus(input_path: Path, output_path: Path) -> dict:
    """Read docs JSONL, write chunks JSONL, return stats dict."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    chunks_per_doc: list[int] = []
    token_counts: list[int] = []

    with (
        input_path.open(encoding="utf-8") as fin,
        output_path.open("w", encoding="utf-8") as fout,
    ):
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("skip malformed JSON line: %s", exc)
                continue
            doc_chunks = list(chunk_doc(doc))
            for chunk in doc_chunks:
                fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            chunks_per_doc.append(len(doc_chunks))
            token_counts.extend(c["token_count"] for c in doc_chunks)

    elapsed = time.perf_counter() - t0
    return {
        "docs": len(chunks_per_doc),
        "chunks": sum(chunks_per_doc),
        "avg_per_doc": (
            round(statistics.mean(chunks_per_doc), 1) if chunks_per_doc else 0
        ),
        "min_per_doc": min(chunks_per_doc, default=0),
        "median_per_doc": statistics.median(chunks_per_doc) if chunks_per_doc else 0,
        "max_per_doc": max(chunks_per_doc, default=0),
        "min_tokens": min(token_counts, default=0),
        "median_tokens": statistics.median(token_counts) if token_counts else 0,
        "max_tokens": max(token_counts, default=0),
        "elapsed_s": round(elapsed, 1),
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(message)s", stream=sys.stderr
    )
    stats = chunk_corpus(INPUT_PATH, OUTPUT_PATH)
    print(f"Docs processed  : {stats['docs']}")
    print(f"Chunks produced : {stats['chunks']}")
    print(f"Avg per doc     : {stats['avg_per_doc']}")
    print(
        f"Min/med/max per doc   : "
        f"{stats['min_per_doc']} / {stats['median_per_doc']} / {stats['max_per_doc']}"
    )
    print(
        f"Min/med/max tokens    : "
        f"{stats['min_tokens']} / {stats['median_tokens']} / {stats['max_tokens']}"
    )
    print(f"Elapsed         : {stats['elapsed_s']}s")
    print(f"Wrote chunks to {OUTPUT_PATH}")
