"""Request logging middleware — emits one JSON line per request."""

import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Emit a structured JSON log line for every HTTP request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        response = await call_next(request)

        # Consume the streaming body so we can read and rebuild the response.
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        latency_ms = round((time.perf_counter() - start) * 1000, 1)

        cost_usd = None
        is_ask = request.method == "POST" and request.url.path == "/ask"
        if is_ask and response.status_code == 200:
            try:
                cost_usd = json.loads(body)["cost_usd"]
            except (json.JSONDecodeError, KeyError):
                cost_usd = None

        logger.info(json.dumps({
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
        }))

        headers = dict(response.headers)
        headers["X-Request-ID"] = request_id
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
