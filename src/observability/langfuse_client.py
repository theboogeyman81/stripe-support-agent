"""Factory for the Langfuse observability client."""

from langfuse import Langfuse

from src.config import Settings


def get_langfuse_client(settings: Settings) -> Langfuse | None:
    """Return a configured Langfuse client, or None if credentials are absent."""
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
