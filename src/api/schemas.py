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
        json_schema_extra={"example": {"status": "ok"}}
    )

    status: str = Field(description="Liveness status; 'ok' if the process is running")


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


class ErrorResponse(BaseModel):
    """Body returned for any unhandled server error."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"detail": "internal server error"}}
    )

    detail: str = Field(
        description="Human-readable error message, never a traceback"
    )
