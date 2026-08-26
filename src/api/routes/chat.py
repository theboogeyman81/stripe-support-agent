"""POST /chat route — runs the agent with per-session conversation history."""

import uuid

from fastapi import APIRouter, HTTPException, Request

from src.agent.agent import run_agent
from src.api.schemas import ChatRequest, ChatResponse
from src.guardrails.off_topic import classify_topic
from src.guardrails.pii_redaction import redact_pii
from src.guardrails.prompt_injection import detect_prompt_injection

router = APIRouter()

_sessions: dict[str, list[dict]] = {}


@router.post("/chat", response_model=ChatResponse)
def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """Run the agent with session history and return an answer."""
    sid = body.session_id if body.session_id in _sessions else str(uuid.uuid4())
    history = _sessions.get(sid, [])
    settings = request.app.state.settings

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

    try:
        result = run_agent(
            question, settings, message_history=history, session_id=sid
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
        trace_id=result.get("trace_id"),
    )
