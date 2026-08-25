"""Request logging middleware — emits one JSON line per request."""

import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.cache.token_stats import accumulate
from src.db.costs import insert_cost

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
        input_tokens = None
        output_tokens = None
        cache_hit = False
        is_ask = request.method == "POST" and request.url.path == "/ask"
        if is_ask and response.status_code == 200:
            try:
                parsed = json.loads(body)
                cost_usd = parsed["cost_usd"]
                input_tokens = parsed["input_tokens"]
                output_tokens = parsed["output_tokens"]
                cache_hit = parsed.get("cache_hit", False)
            except (json.JSONDecodeError, KeyError):
                pass
            else:
                redis_client = getattr(request.app.state, "redis_client", None)
                accumulate(redis_client, input_tokens, output_tokens, cost_usd)
                postgres_url = getattr(request.app.state, "postgres_url", "")
                insert_cost(
                    postgres_url, input_tokens, output_tokens, cost_usd, cache_hit
                )

        logger.info(json.dumps({
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }))

        headers = dict(response.headers)
        headers["X-Request-ID"] = request_id
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
