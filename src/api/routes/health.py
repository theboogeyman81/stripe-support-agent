"""GET /health and GET /ready health-check routes."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.rag.vectorstore import COLLECTION, QdrantStore

router = APIRouter()


class HealthResponse(BaseModel):
    status: str


class ReadyCheck(BaseModel):
    qdrant: str


class ReadyResponse(BaseModel):
    status: str
    checks: ReadyCheck


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe — confirms the process is running."""
    return HealthResponse(status="ok")


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    """Readiness probe — confirms Qdrant is reachable."""
    settings = request.app.state.settings
    try:
        store = QdrantStore(
            url=settings.qdrant_url,
            collection=COLLECTION,
            api_key=settings.qdrant_api_key,
        )
        store.ping()
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "checks": {"qdrant": "ok"}},
        )
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "checks": {"qdrant": "unreachable"}},
        )
