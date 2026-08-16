"""FastAPI application factory for the Stripe Support Agent API."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import voyageai
from fastapi import FastAPI

from src.api.error_handlers import register_error_handlers
from src.api.middleware import LoggingMiddleware
from src.api.routes import ask as ask_routes
from src.api.routes import chat as chat_routes
from src.api.routes import costs as costs_routes
from src.api.routes import feedback as feedback_routes
from src.api.routes import health as health_routes
from src.api.routes import ingest as ingest_routes
from src.api.routes import metrics as metrics_routes
from src.cache.redis_client import get_redis_client
from src.config import Settings
from src.rag.embedder import VoyageEmbedder

APP_VERSION = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct and return the FastAPI application with lifespan and routes."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        s = settings or Settings()
        app.state.settings = s
        try:
            client = get_redis_client(s)
            client.ping()
            app.state.redis_status = "ok"
            app.state.redis_client = client
            print("Redis: connected")
        except Exception as exc:
            app.state.redis_status = f"error: {exc}"
            app.state.redis_client = None
            print(f"WARNING: Redis unavailable — {exc}")
        try:
            voyage_client = voyageai.Client(api_key=s.voyage_api_key)
            app.state.embedder = VoyageEmbedder(client=voyage_client)
            print("Embedder: ready")
        except Exception as exc:
            app.state.embedder = None
            print(f"WARNING: Embedder unavailable — {exc}")
        if s.postgres_url:
            try:
                from src.db.costs import ensure_costs_table
                ensure_costs_table(s.postgres_url)
                app.state.postgres_url = s.postgres_url
                print("Postgres: request_costs table ready")
            except Exception as exc:
                app.state.postgres_url = ""
                print(f"WARNING: Postgres unavailable — {exc}")
        else:
            app.state.postgres_url = ""
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
    app.include_router(chat_routes.router)
    app.include_router(costs_routes.router)
    app.include_router(feedback_routes.router)
    app.include_router(ingest_routes.router)
    app.include_router(health_routes.router)
    app.include_router(metrics_routes.router)
    app.add_middleware(LoggingMiddleware)
    register_error_handlers(app)

    return app


app = create_app()
