"""POST /admin/ingest route — triggers the full ingestion pipeline."""

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from src.api.deps import check_admin_key
from src.api.schemas import IngestRequest, IngestResponse
from src.ingest import run_ingest

router = APIRouter(prefix="/admin")


@router.post("/ingest", response_model=IngestResponse)
def ingest_pipeline(
    request: Request,
    body: IngestRequest = Body(default_factory=IngestRequest),
    _: None = Depends(check_admin_key),
) -> IngestResponse:
    """Trigger load → chunk → embed → upsert and return pipeline statistics."""
    try:
        result = run_ingest(request.app.state.settings, body.recreate)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ingest error: {e}")
    return IngestResponse(**result)
