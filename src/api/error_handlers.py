"""Global exception handlers — catch unhandled errors and return a safe response."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def _handle_unhandled_exception(
    request: Request, exc: Exception
) -> JSONResponse:
    """Log the full traceback and return a generic 500 body with no internal detail."""
    logger.error("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error"},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI app."""
    app.add_exception_handler(Exception, _handle_unhandled_exception)
