"""Generator: calls Gemini to produce a grounded answer from retrieved chunks."""

from google import genai

from src.config import Settings

GEMINI_MODEL = "gemini-2.5-flash"
# Verify current rates at https://ai.google.dev/pricing before committing.
INPUT_PRICE_PER_M = 0.30   # USD per 1M input tokens
OUTPUT_PRICE_PER_M = 2.50  # USD per 1M output tokens


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


def generate(question: str, chunks: list[dict]) -> dict:
    """Call Gemini with the RAG prompt and return answer, token counts, and cost."""
    if not question.strip():
        raise ValueError("question must not be empty")
    if not chunks:
        raise ValueError("chunks must not be empty")

    settings = Settings()
    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = build_prompt(question, chunks)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)

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
