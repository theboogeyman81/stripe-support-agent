"""Entry point for `python -m src.api`; starts the uvicorn server."""

import logging
import sys

import uvicorn

from src.config import Settings


def main() -> None:
    """Read host/port from Settings and start the uvicorn server."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    settings = Settings()
    uvicorn.run(
        "src.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
