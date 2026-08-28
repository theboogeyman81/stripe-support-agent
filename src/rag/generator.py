"""Generator: calls Gemini to produce a grounded answer from retrieved chunks."""

import redis as redis_lib
from google import genai

from src.cache.exact_match import cache_key, get_cached, set_cached
from src.config import Settings
from src.rag.circuit_breaker import is_circuit_open, record_failure, record_success

GEMINI_MODEL_PRIMARY = "gemini-2.5-flash"
GEMINI_MODEL_SECONDARY = "gemini-2.0-flash"
# Verify current rates at https://ai.google.dev/pricing before committing.
INPUT_PRICE_PER_M = 0.30   # USD per 1M input tokens
OUTPUT_PRICE_PER_M = 2.50  # USD per 1M output tokens
APOLOGY_ANSWER = (
    "I'm sorry, I'm temporarily unable to answer. "
    "Please try again shortly or contact Stripe support."
)


def build_prompt(question: str, chunks: list[dict]) -> str:
    """Format retrieved chunks and question into a RAG prompt for Gemini."""
    excerpts = []
    for i, chunk in enumerate(chunks, 1):
        excerpts.append(
            f"[{i}] {chunk['doc_title']}\n"
            f"URL: {chunk['doc_url']}\n"
            f"{chunk['text']}"
        )
    excerpts_block = "\n\n".join(excerpts)
    return (
        "You are a Stripe support assistant. Answer the user's question using ONLY\n"
        "the provided documentation excerpts below. Do not use outside knowledge.\n"
        "Cite each fact with its source number, e.g. [1] or [2].\n"
        "If the excerpts don't contain enough information, say so — do not guess.\n\n"
        "--- Documentation excerpts ---\n\n"
        f"{excerpts_block}\n\n"
        "--- Question ---\n"
        f"{question}\n\n"
        "--- Answer ---"
    )


def _call_model(model: str, prompt: str, settings: Settings) -> dict:
    """Call a single Gemini model; return answer, token counts, and cost."""
    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    answer = response.text.strip()
    input_tokens = response.usage_metadata.prompt_token_count
    output_tokens = response.usage_metadata.candidates_token_count
    cost_usd = (
        (input_tokens / 1_000_000) * INPUT_PRICE_PER_M
        + (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_M
    )
    return {
        "answer": answer,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }


def generate(
    question: str,
    chunks: list[dict],
    redis_client: redis_lib.Redis | None = None,
    cache_ttl: int = 3600,
) -> dict:
    """Call Gemini with the RAG prompt and return answer, token counts, and cost."""
    if not question.strip():
        raise ValueError("question must not be empty")
    if not chunks:
        raise ValueError("chunks must not be empty")

    prompt = build_prompt(question, chunks)
    settings = Settings()

    # Exact-match cache lookup
    key: str | None = None
    if redis_client is not None:
        key = cache_key(GEMINI_MODEL_PRIMARY, prompt)
        hit = get_cached(redis_client, key)
        if hit is not None:
            return {**hit, "cache_hit": True}

    # Fallback chain: primary → secondary → apology
    start_level = 1 if is_circuit_open(redis_client) else 0
    models = [GEMINI_MODEL_PRIMARY, GEMINI_MODEL_SECONDARY]
    for level, model in enumerate(models[start_level:], start=start_level):
        try:
            result = _call_model(model, prompt, settings)
            if level == 0:
                record_success(redis_client)
            result["cache_hit"] = False
            result["fallback_level"] = level
            if key is not None:
                set_cached(redis_client, key, result, cache_ttl)
            return result
        except Exception as exc:
            print(f"[WARNING] Gemini model {model} failed: {exc}")
            if level == 0:
                record_failure(redis_client)

    return {
        "answer": APOLOGY_ANSWER,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "cache_hit": False,
        "fallback_level": 2,
    }
