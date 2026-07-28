"""POST /admin/ingest route — triggers the full ingestion pipeline."""

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request

from src.api.schemas import IngestRequest, IngestResponse
from src.ingest import run_ingest

router = APIRouter(prefix="/admin")


def _check_admin_key(
    request: Request,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    """Validate the X-Admin-Key header against settings."""
    if x_admin_key is None:
        raise HTTPException(status_code=401, detail="missing admin key")
    if x_admin_key != request.app.state.settings.admin_api_key:
        raise HTTPException(status_code=403, detail="invalid admin key")


@router.post("/ingest", response_model=IngestResponse)
def ingest_pipeline(
    request: Request,
    body: IngestRequest = Body(default_factory=IngestRequest),
    _: None = Depends(_check_admin_key),
) -> IngestResponse:
    """Trigger load → chunk → embed → upsert and return pipeline statistics."""
    try:
        result = run_ingest(request.app.state.settings, body.recreate)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ingest error: {e}")
    return IngestResponse(**result)
