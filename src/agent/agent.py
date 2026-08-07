"""Pydantic AI agent wired to Gemini 2.5 Flash for Stripe support questions."""

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from src.agent.tools import calculate, create_ticket, lookup_user, search_docs
from src.config import Settings
from src.observability.langfuse_client import get_langfuse_client

GEMINI_MODEL = "gemini-2.5-flash"
INPUT_PRICE_PER_M = 0.30  # USD per 1M input tokens
OUTPUT_PRICE_PER_M = 2.50  # USD per 1M output tokens

SYSTEM_PROMPT = """
You are a Stripe support assistant. Help users with questions about Stripe
products, APIs, billing, and accounts.

## Tool selection rules

- Call `search_docs` when the user asks a factual question about Stripe
  products, APIs, features, or documentation.
- Call `lookup_user` when the user provides their email address or asks about
  their account, plan, or account status.
- Call `create_ticket` when the user reports a billing problem, account issue,
  or complaint that cannot be resolved from documentation alone. If the user
  has provided an email, call `lookup_user` first so the ticket can reference
  their account.
- Call `calculate` when a fee, amount, or arithmetic calculation is needed.

## Behaviour

- If `search_docs` returns no relevant results, say so honestly.
- If `lookup_user` returns no user, relay that and ask the user to verify
  their email.
- Keep answers concise — one to three sentences after tool results unless more
  detail is clearly needed.
""".strip()


def create_agent(settings: Settings) -> Agent:
    """Return a configured Pydantic AI Agent bound to Gemini 2.5 Flash."""
    model = GoogleModel(
        GEMINI_MODEL,
        provider=GoogleProvider(api_key=settings.gemini_api_key),
    )
    return Agent(
        model,
        system_prompt=SYSTEM_PROMPT,
        tools=[search_docs, calculate, create_ticket, lookup_user],
        deps_type=Settings,
    )


def run_agent(
    question: str,
    settings: Settings,
    message_history: list[dict] | None = None,
    session_id: str | None = None,
) -> dict:
    """Run the agent on a question; return answer, tokens, cost, and history."""
    if not question.strip():
        raise ValueError("question must not be empty")
    agent = create_agent(settings)
    history = (
        ModelMessagesTypeAdapter.validate_python(message_history)
        if message_history
        else None
    )
    result = agent.run_sync(question, deps=settings, message_history=history)
    usage = result.usage
    input_tokens = usage.input_tokens or 0
    output_tokens = usage.output_tokens or 0
    answer = result.output
    cost_usd = (
        (input_tokens / 1_000_000) * INPUT_PRICE_PER_M
        + (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_M
    )
    trace_id: str | None = None
    client = get_langfuse_client(settings)
    if client:
        trace = client.start_observation(
            name="stripe-support-chat",
            as_type="span",
            input=question,
            **({"metadata": {"session_id": session_id}} if session_id else {}),
        )
        trace_id = trace.trace_id
        trace.start_observation(
            name=GEMINI_MODEL,
            as_type="generation",
            model=GEMINI_MODEL,
            input=question,
            output=answer,
            usage_details={"input": input_tokens, "output": output_tokens},
            cost_details={"total": cost_usd},
        ).end()
        trace.update(output=answer)
        trace.end()
        client.flush()
    return {
        "answer": answer,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "message_history": ModelMessagesTypeAdapter.dump_python(result.all_messages()),
        "trace_id": trace_id,
    }
