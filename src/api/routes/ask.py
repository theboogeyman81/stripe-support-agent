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
from src.guardrails.hallucination import UNGROUNDED_FALLBACK, check_grounding
from src.guardrails.off_topic import classify_topic
from src.guardrails.pii_redaction import redact_pii
from src.guardrails.prompt_injection import detect_prompt_injection
from src.guardrails.safety import UNSAFE_FALLBACK, check_safety
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

    redaction = redact_pii(body.question)
    if redaction.pii_detected:
        print(f"[DEBUG] PII redacted: {[r['type'] for r in redaction.replacements]}")
    question = redaction.redacted_text

    injection = detect_prompt_injection(question)
    if injection.is_injection:
        print(f"[WARNING] Prompt injection detected: {injection.matched_pattern}")
        raise HTTPException(
            status_code=400,
            detail="Request rejected: prompt injection detected.",
        )

    topic = classify_topic(question)
    if topic.is_off_topic:
        print(f"[WARNING] Off-topic query rejected: domain={topic.reason}")
        raise HTTPException(
            status_code=400,
            detail=(
                "This question doesn't appear to be about Stripe or payments. "
                "Please ask about Stripe products, APIs, or billing."
            ),
        )

    # Semantic cache lookup — before retrieval
    if redis_client is not None and embedder is not None:
        sem_hit = semantic_search(redis_client, embedder, question, threshold)
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
        chunks = retrieve(question, body.top_k)
        result = generate(
            question,
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

    safety = check_safety(result["answer"])
    if not safety.is_safe:
        print(f"[WARNING] Unsafe output detected: category={safety.reason}")
        result["answer"] = UNSAFE_FALLBACK

    cache_answer = safety.is_safe
    if safety.is_safe:
        grounding = check_grounding(result["answer"], chunks)
        if not grounding.is_grounded:
            print(
                f"[WARNING] Ungrounded answer detected "
                f"(overlap={grounding.overlap_score:.2f}), replacing with fallback"
            )
            result["answer"] = UNGROUNDED_FALLBACK
        cache_answer = grounding.is_grounded

    seen_urls: set[str] = set()
    sources: list[SourceItem] = []
    for chunk in chunks:
        if chunk["doc_url"] not in seen_urls:
            seen_urls.add(chunk["doc_url"])
            sources.append(SourceItem(title=chunk["doc_title"], url=chunk["doc_url"]))

    # Semantic cache store — only for safe and grounded answers
    if redis_client is not None and embedder is not None and cache_answer:
        semantic_store(
            redis_client,
            embedder,
            question,
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
