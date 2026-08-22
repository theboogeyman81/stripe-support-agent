"""Pure retrieval evaluation metrics: Recall@k and Reciprocal Rank."""


def recall_at_k(retrieved_urls: list[str], ideal_urls: list[str]) -> float:
    """Return 1.0 if any retrieved URL is in ideal_urls, else 0.0."""
    ideal_set = set(ideal_urls)
    return 1.0 if any(u in ideal_set for u in retrieved_urls) else 0.0


def reciprocal_rank(retrieved_urls: list[str], ideal_urls: list[str]) -> float:
    """Return 1/rank of the first matching URL, or 0.0 if no match."""
    ideal_set = set(ideal_urls)
    for rank, url in enumerate(retrieved_urls, 1):
        if url in ideal_set:
            return 1.0 / rank
    return 0.0
