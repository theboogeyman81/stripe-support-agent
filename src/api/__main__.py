"""Entry point for `python -m src.api`; starts the uvicorn server."""

import uvicorn

from src.config import Settings


def main() -> None:
    """Read host/port from Settings and start the uvicorn server."""
    settings = Settings()
    uvicorn.run(
        "src.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
