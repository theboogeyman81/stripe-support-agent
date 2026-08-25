"""Semantic cache helpers: cosine similarity, search, and store."""

import json
import math
import uuid

import redis

from src.rag.embedder import VoyageEmbedder

SEMANTIC_PREFIX = "semantic:"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity in [0, 1]; 0.0 if either vector is zero."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_search(
    redis_client: redis.Redis,
    embedder: VoyageEmbedder,
    question: str,
    threshold: float,
) -> dict | None:
    """Return best cached result above threshold, or None on miss or error."""
    try:
        query_vec = embedder.embed_query(question)
        best_score, best_entry = -1.0, None
        for key in redis_client.scan_iter(f"{SEMANTIC_PREFIX}*"):
            raw = redis_client.get(key)
            if raw is None:
                continue
            try:
                entry = json.loads(raw)
            except Exception:
                continue
            sim = cosine_similarity(query_vec, entry["embedding"])
            if sim > best_score:
                best_score, best_entry = sim, entry
        if best_entry is not None and best_score >= threshold:
            return {k: v for k, v in best_entry.items() if k != "embedding"}
        return None
    except Exception:
        return None


def semantic_store(
    redis_client: redis.Redis,
    embedder: VoyageEmbedder,
    question: str,
    value: dict,
    ttl: int,
) -> None:
    """Embed question and store result under a new semantic:<uuid> key."""
    try:
        embedding = embedder.embed_query(question)
        entry = {**value, "embedding": embedding}
        key = f"{SEMANTIC_PREFIX}{uuid.uuid4().hex}"
        redis_client.setex(key, ttl, json.dumps(entry))
    except Exception:
        pass
