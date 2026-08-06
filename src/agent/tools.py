"""Pydantic AI tools available to the Stripe support agent."""

from pydantic_ai import RunContext

from src.config import Settings
from src.rag.vectorstore import retrieve


def search_docs(ctx: RunContext[Settings], query: str) -> str:
    """Search Stripe docs for chunks relevant to query; return formatted text."""
    if not query.strip():
        raise ValueError("query must not be empty")
    chunks = retrieve(query, top_k=5)
    if not chunks:
        return "No relevant documentation found."
    sections = []
    for i, chunk in enumerate(chunks, 1):
        sections.append(
            f"[{i}] {chunk['doc_title']}\n"
            f"URL: {chunk['doc_url']}\n"
            f"{chunk['text']}"
        )
    return "\n\n".join(sections)
