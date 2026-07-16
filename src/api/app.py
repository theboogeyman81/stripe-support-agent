"""FastAPI application factory for the Stripe Support Agent API."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from src.api.routes import ask as ask_routes
from src.api.routes import ingest as ingest_routes
from src.config import Settings

APP_VERSION = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct and return the FastAPI application with lifespan and routes."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.settings = settings or Settings()
        yield

    app = FastAPI(
        title="Stripe Support Agent",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    @app.get("/")
    def root() -> dict:
        """Return service status."""
        return {
            "status": "ok",
            "service": "stripe-support-agent",
            "version": APP_VERSION,
        }

    app.include_router(ask_routes.router)
    app.include_router(ingest_routes.router)

    return app


app = create_app()
