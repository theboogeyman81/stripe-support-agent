"""GET /admin/costs route — time-windowed aggregate cost query."""

from fastapi import APIRouter, Depends, Query, Request

from src.api.deps import check_admin_key
from src.api.schemas import CostsResponse
from src.db.costs import query_costs

router = APIRouter(prefix="/admin")


@router.get("/costs", response_model=CostsResponse)
def costs_endpoint(
    request: Request,
    window: str = Query(default="7d", pattern=r"^\d+d$"),
    _: None = Depends(check_admin_key),
) -> CostsResponse:
    """Return aggregate cost/token stats for the requested time window."""
    days = int(window.rstrip("d"))
    postgres_url = getattr(request.app.state, "postgres_url", "")
    data = query_costs(postgres_url, days)
    return CostsResponse(window=window, **data)
