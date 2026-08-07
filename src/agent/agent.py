"""Pydantic AI agent wired to Gemini 2.5 Flash for Stripe support questions."""

from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from src.agent.tools import calculate, create_ticket, lookup_user, search_docs
from src.config import Settings

GEMINI_MODEL = "gemini-2.5-flash"
INPUT_PRICE_PER_M = 0.30  # USD per 1M input tokens
OUTPUT_PRICE_PER_M = 2.50  # USD per 1M output tokens

SYSTEM_PROMPT = (
    "You are a Stripe support assistant. "
    "Answer questions about Stripe products and APIs accurately and concisely."
)


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
