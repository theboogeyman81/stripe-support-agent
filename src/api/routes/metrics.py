"""GET /metrics route — cache hit/miss counters and token totals."""

from fastapi import APIRouter, Request

from src.api.schemas import CacheTypeMetrics, MetricsResponse, TokenStats
from src.cache.metrics import get_metrics
from src.cache.token_stats import get_token_stats

router = APIRouter()


@router.get("/metrics", response_model=MetricsResponse)
def metrics_endpoint(request: Request) -> MetricsResponse:
    """Return cache hit/miss counters and lifetime token/cost totals."""
    redis_client = getattr(request.app.state, "redis_client", None)
    data = get_metrics(redis_client)
    ts = get_token_stats(redis_client)
    return MetricsResponse(
        semantic=CacheTypeMetrics(**data["semantic"]),
        exact=CacheTypeMetrics(**data["exact"]),
        total_requests=data["total_requests"],
        tokens=TokenStats(**ts),
    )
