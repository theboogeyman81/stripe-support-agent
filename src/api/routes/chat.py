"""POST /chat route — runs the agent with per-session conversation history."""

import uuid

from fastapi import APIRouter, HTTPException, Request

from src.agent.agent import run_agent
from src.api.schemas import ChatRequest, ChatResponse

router = APIRouter()

_sessions: dict[str, list[dict]] = {}


@router.post("/chat", response_model=ChatResponse)
def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """Run the agent with session history and return an answer."""
    sid = body.session_id if body.session_id in _sessions else str(uuid.uuid4())
    history = _sessions.get(sid, [])
    settings = request.app.state.settings
    try:
        result = run_agent(
            body.question, settings, message_history=history, session_id=sid
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")
    _sessions[sid] = result["message_history"]
    return ChatResponse(
        session_id=sid,
        answer=result["answer"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cost_usd=result["cost_usd"],
    )
