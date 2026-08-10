"""Pydantic AI agent wired to Gemini 2.5 Flash for Stripe support questions."""

from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from src.agent.tools import calculate, create_ticket, lookup_user, search_docs
from src.config import Settings

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


def run_agent(question: str, settings: Settings) -> dict:
    """Run the agent on a question and return answer, token counts, and cost."""
    if not question.strip():
        raise ValueError("question must not be empty")
    agent = create_agent(settings)
    result = agent.run_sync(question, deps=settings)
    usage = result.usage
    input_tokens = usage.input_tokens or 0
    output_tokens = usage.output_tokens or 0
    cost_usd = (
        (input_tokens / 1_000_000) * INPUT_PRICE_PER_M
        + (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_M
    )
    return {
        "answer": result.output,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }
