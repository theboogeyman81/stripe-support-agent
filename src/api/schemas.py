"""Centralised Pydantic request/response models for all API endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class SourceItem(BaseModel):
    """A single source document referenced in an answer."""

    title: str = Field(description="Human-readable title of the Stripe docs page")
    url: str = Field(description="Canonical URL of the source page")


class AskRequest(BaseModel):
    """Body for POST /ask."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "How do I create a PaymentIntent?",
                "top_k": 5,
            }
        }
    )

    question: str = Field(
        min_length=1,
        description="The question to answer using Stripe documentation",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        description="Number of chunks to retrieve from the vector store",
    )


class AskResponse(BaseModel):
    """Response from POST /ask."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "Pass amount and currency to paymentIntents.create().",
                "sources": [
                    {
                        "title": "PaymentIntents",
                        "url": "https://docs.stripe.com/payments/payment-intents",
                    }
                ],
                "input_tokens": 1024,
                "output_tokens": 128,
                "cost_usd": 0.000312,
                "cache_hit": False,
            }
        }
    )

    answer: str = Field(
        description="Grounded answer generated from retrieved Stripe documentation"
    )
    sources: list[SourceItem] = Field(
        description="Deduplicated source pages used to generate the answer"
    )
    input_tokens: int = Field(description="Tokens in the prompt sent to the LLM")
    output_tokens: int = Field(description="Tokens in the LLM response")
    cost_usd: float = Field(description="Estimated USD cost of the LLM call")
    cache_hit: bool = Field(False, description="True if answer was served from cache")
    degraded: bool = Field(
        False,
        description=(
            "True when a guardrail replaced the answer or a fallback model was used"
        ),
    )
    degradation_reason: str | None = Field(
        None,
        description=(
            "First degradation cause: 'unsafe_output', 'ungrounded', "
            "'uncited', 'model_fallback', 'service_unavailable'"
        ),
    )
    fallback_level: int = Field(
        0,
        description="Model tier used: 0=primary, 1=secondary, 2=apology",
    )


class IngestRequest(BaseModel):
    """Body for POST /admin/ingest."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"recreate": False}}
    )

    recreate: bool = Field(
        default=False,
        description="When true, drop and recreate the Qdrant collection first",
    )


class IngestResponse(BaseModel):
    """Response from POST /admin/ingest."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "docs_loaded": 1,
                "chunks_produced": 4319,
                "vectors_embedded": 4319,
                "vectors_skipped": 0,
                "points_upserted": 4319,
                "embed_cost_usd": 0.0,
                "cached_steps": [],
            }
        }
    )

    docs_loaded: int = Field(description="Source documents fetched and parsed")
    chunks_produced: int = Field(description="Text chunks created by the chunker")
    vectors_embedded: int = Field(description="Chunks sent to the embedding model")
    vectors_skipped: int = Field(
        description="Chunks skipped because embeddings already existed"
    )
    points_upserted: int = Field(
        description="Vectors written to the Qdrant collection"
    )
    embed_cost_usd: float = Field(description="Estimated USD cost of embedding calls")
    cached_steps: list[str] = Field(
        description="Pipeline steps skipped due to caching"
    )


class HealthResponse(BaseModel):
    """Response from GET /health."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"status": "ok", "redis": "ok"}}
    )

    status: str = Field(description="Liveness status; 'ok' if the process is running")
    redis: str | None = Field(None, description="Redis status; 'ok' or 'error: <msg>'")


class TokenStats(BaseModel):
    """Lifetime token and cost totals across all /ask requests."""

    total_input: int = Field(description="Cumulative prompt tokens")
    total_output: int = Field(description="Cumulative response tokens")
    total_cost_usd: float = Field(description="Cumulative estimated spend in USD")
    total_requests: int = Field(description="Total /ask requests recorded")


class CacheTypeMetrics(BaseModel):
    """Hit/miss counts for one cache layer."""

    hits: int = Field(description="Number of cache hits")
    misses: int = Field(description="Number of cache misses")
    hit_rate: float = Field(
        description="hits / (hits + misses); 0.0 if no requests yet"
    )


class MetricsResponse(BaseModel):
    """Response from GET /metrics."""

    semantic: CacheTypeMetrics = Field(description="Semantic cache counters")
    exact: CacheTypeMetrics = Field(description="Exact-match cache counters")
    total_requests: int = Field(
        description="All /ask calls that had cache active"
    )
    tokens: TokenStats = Field(description="Lifetime token and cost totals")


class ReadyCheck(BaseModel):
    """Per-dependency readiness status nested inside ReadyResponse."""

    qdrant: str = Field(description="Qdrant reachability; 'ok' or 'unreachable'")


class ReadyResponse(BaseModel):
    """Response from GET /ready."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "checks": {"qdrant": "ok"},
            }
        }
    )

    status: str = Field(description="Overall readiness; 'ok' or 'degraded'")
    checks: ReadyCheck = Field(description="Per-dependency readiness breakdown")


class ChatRequest(BaseModel):
    """Body for POST /chat."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": None,
                "question": "What is a PaymentIntent?",
            }
        }
    )

    session_id: str | None = Field(
        default=None,
        description="Conversation session id; omit to start a new session",
    )
    question: str = Field(min_length=1, description="User's message")


class ChatResponse(BaseModel):
    """Response from POST /chat."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "3f2a1b4c-...",
                "answer": "A PaymentIntent guides you through the payment process.",
                "input_tokens": 400,
                "output_tokens": 80,
                "cost_usd": 0.0003,
            }
        }
    )

    session_id: str = Field(description="Session id to pass back on the next turn")
    answer: str = Field(description="Agent's response")
    input_tokens: int = Field(description="Tokens in the prompt sent to the LLM")
    output_tokens: int = Field(description="Tokens in the LLM response")
    cost_usd: float = Field(description="Estimated USD cost of the LLM call")
    trace_id: str | None = Field(
        default=None,
        description="Langfuse trace ID; pass to POST /feedback to score this turn",
    )


class FeedbackRequest(BaseModel):
    """Body for POST /feedback."""

    trace_id: str = Field(description="Langfuse trace ID from POST /chat response")
    value: int = Field(ge=0, le=1, description="1 = thumbs up, 0 = thumbs down")
    comment: str | None = Field(default=None, description="Optional freetext comment")


class FeedbackResponse(BaseModel):
    """Response from POST /feedback."""

    success: bool = Field(description="True if the score was submitted to Langfuse")


class CostsResponse(BaseModel):
    """Response from GET /admin/costs."""

    window: str = Field(description="Lookback window echoed from the query param")
    total_requests: int = Field(description="Requests in the window")
    cache_hits: int = Field(description="Requests served from cache in the window")
    total_input_tokens: int = Field(description="Sum of prompt tokens in the window")
    total_output_tokens: int = Field(description="Sum of response tokens in the window")
    total_cost_usd: float = Field(description="Sum of estimated spend in the window")


class ErrorResponse(BaseModel):
    """Body returned for any unhandled server error."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"detail": "internal server error"}}
    )

    detail: str = Field(
        description="Human-readable error message, never a traceback"
    )
