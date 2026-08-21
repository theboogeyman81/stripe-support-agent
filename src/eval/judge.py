"""Custom LLM-as-judge for agent behaviour: tool choice and tone."""

import json
import typing as t

from google import genai

from src.config import Settings

TOOL_CHOICE_PROMPT = """\
You are evaluating a customer support agent's tool selection.

The agent has these tools with the following selection rules:
- search_docs: call for factual questions about Stripe products, APIs, or documentation
- lookup_user: call when the user provides an email or asks about their account
- create_ticket: call for billing problems or complaints documentation cannot resolve
- calculate: call for fee calculations or arithmetic

Question asked:
{question}

Tools the agent called (in order): {tools_called}

Agent's final answer:
{answer}

Score the tool selection:
- 1.0 = correct tool(s) called; no unnecessary tools invoked
- 0.5 = partially correct (right tool called but also an unnecessary one, or suboptimal)
- 0.0 = wrong tool called, or no tool called when one was clearly needed

Respond with ONLY a JSON object — no markdown fences, no extra text:
{{"score": 1, "rationale": "<one sentence>"}}"""

TONE_PROMPT = """\
You are evaluating a customer support agent's response quality.

Question asked:
{question}

Agent's answer:
{answer}

Score the tone and quality:
- 1.0 = concise (1-3 sentences), honest, and professional
- 0.5 = minor issues: slightly too long, mild hedging, or minor informality
- 0.0 = hallucinating, off-topic, rude, or clearly incorrect

Respond with ONLY a JSON object — no markdown fences, no extra text:
{{"score": 1, "rationale": "<one sentence>"}}"""


def extract_tool_calls(message_history: list[dict]) -> list[str]:
    """Return tool names called, in order, from serialised Pydantic AI messages."""
    names: list[str] = []
    for message in message_history:
        for part in message.get("parts", []):
            if part.get("part_kind") == "tool-call":
                names.append(part["tool_name"])
    return names


def score_tool_choice(
    question: str,
    tools_called: list[str],
    answer: str,
    client: genai.Client,
    model: str,
) -> dict[str, t.Any]:
    """Score tool selection quality; returns {'score': float, 'rationale': str}."""
    prompt = TOOL_CHOICE_PROMPT.format(
        question=question,
        tools_called=", ".join(tools_called) if tools_called else "(none)",
        answer=answer,
    )
    raw = client.models.generate_content(model=model, contents=prompt).text.strip()
    try:
        parsed = json.loads(raw)
        return {
            "score": float(parsed["score"]),
            "rationale": str(parsed["rationale"]),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return {"score": 0.5, "rationale": "parse error"}


def score_tone(
    question: str,
    answer: str,
    client: genai.Client,
    model: str,
) -> dict[str, t.Any]:
    """Score answer tone and quality; returns {'score': float, 'rationale': str}."""
    prompt = TONE_PROMPT.format(question=question, answer=answer)
    raw = client.models.generate_content(model=model, contents=prompt).text.strip()
    try:
        parsed = json.loads(raw)
        return {
            "score": float(parsed["score"]),
            "rationale": str(parsed["rationale"]),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return {"score": 0.5, "rationale": "parse error"}


def build_judge_client(settings: Settings) -> genai.Client:
    """Return a google-genai Client configured from Settings."""
    return genai.Client(api_key=settings.gemini_api_key)
