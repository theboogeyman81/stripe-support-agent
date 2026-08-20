"""POST /feedback route — writes a user score to a Langfuse trace."""

from fastapi import APIRouter, HTTPException, Request

from src.api.schemas import FeedbackRequest, FeedbackResponse
from src.observability.langfuse_client import get_langfuse_client

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
def feedback(request: Request, body: FeedbackRequest) -> FeedbackResponse:
    """Submit a thumbs up/down score to the Langfuse trace for a chat turn."""
    settings = request.app.state.settings
    client = get_langfuse_client(settings)
    if client is None:
        raise HTTPException(status_code=503, detail="Langfuse is not configured")
    client.create_score(
        trace_id=body.trace_id,
        name="user-feedback",
        value=body.value,
        comment=body.comment,
    )
    client.flush()
    return FeedbackResponse(success=True)
