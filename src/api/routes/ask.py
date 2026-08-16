"""POST /ask route — retrieves chunks and generates a Gemini answer."""

from fastapi import APIRouter, HTTPException, Request

from src.api.schemas import AskRequest, AskResponse, SourceItem
from src.cache.metrics import (
    EXACT_HITS,
    EXACT_MISSES,
    SEMANTIC_HITS,
    SEMANTIC_MISSES,
    increment,
)
from src.cache.semantic import semantic_search, semantic_store
from src.rag.generator import generate
from src.rag.vectorstore import retrieve

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request) -> AskResponse:
    """Retrieve relevant chunks and generate a grounded answer."""
    redis_client = getattr(request.app.state, "redis_client", None)
    embedder = getattr(request.app.state, "embedder", None)
    cache_ttl = getattr(request.app.state.settings, "cache_ttl_seconds", 3600)
    threshold = getattr(
        request.app.state.settings, "semantic_similarity_threshold", 0.95
    )

    # Semantic cache lookup — before retrieval
    if redis_client is not None and embedder is not None:
        sem_hit = semantic_search(redis_client, embedder, body.question, threshold)
        if sem_hit is not None:
            increment(redis_client, SEMANTIC_HITS)
            return AskResponse(
                answer=sem_hit["answer"],
                sources=[SourceItem(**s) for s in sem_hit["sources"]],
                input_tokens=sem_hit["input_tokens"],
                output_tokens=sem_hit["output_tokens"],
                cost_usd=sem_hit["cost_usd"],
                cache_hit=True,
            )
        increment(redis_client, SEMANTIC_MISSES)

    try:
        chunks = retrieve(body.question, body.top_k)
        result = generate(
            body.question,
            chunks,
            redis_client=redis_client,
            cache_ttl=cache_ttl,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")

    if redis_client is not None:
        if result["cache_hit"]:
            increment(redis_client, EXACT_HITS)
        else:
            increment(redis_client, EXACT_MISSES)

    seen_urls: set[str] = set()
    sources: list[SourceItem] = []
    for chunk in chunks:
        if chunk["doc_url"] not in seen_urls:
            seen_urls.add(chunk["doc_url"])
            sources.append(SourceItem(title=chunk["doc_title"], url=chunk["doc_url"]))

    # Semantic cache store — after full pipeline
    if redis_client is not None and embedder is not None:
        semantic_store(
            redis_client,
            embedder,
            body.question,
            {
                "answer": result["answer"],
                "sources": [s.model_dump() for s in sources],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "cost_usd": result["cost_usd"],
            },
            cache_ttl,
        )

    return AskResponse(
        answer=result["answer"],
        sources=sources,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cost_usd=result["cost_usd"],
        cache_hit=result.get("cache_hit", False),
    )
