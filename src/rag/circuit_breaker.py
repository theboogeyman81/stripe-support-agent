"""Redis-backed circuit breaker for the primary Gemini model."""

import redis as redis_lib

FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 60
_KEY_OPEN = "cb:open"
_KEY_FAILURES = "cb:failures"


def is_circuit_open(redis_client: redis_lib.Redis | None) -> bool:
    """Return True if the circuit is open and primary model should be skipped."""
    if redis_client is None:
        return False
    try:
        return bool(redis_client.exists(_KEY_OPEN))
    except Exception:
        return False  # fail open — prefer trying the primary over skipping it


def record_failure(redis_client: redis_lib.Redis | None) -> None:
    """Increment failure counter; open circuit if threshold is reached."""
    if redis_client is None:
        return
    try:
        count = redis_client.incr(_KEY_FAILURES)
        if count >= FAILURE_THRESHOLD:
            redis_client.set(_KEY_OPEN, "1", ex=COOLDOWN_SECONDS)
            print(
                f"[WARNING] Circuit breaker opened — "
                f"skipping primary model for {COOLDOWN_SECONDS}s"
            )
    except Exception:
        pass


def record_success(redis_client: redis_lib.Redis | None) -> None:
    """Reset failure counter on primary success; leave cooldown TTL intact."""
    if redis_client is None:
        return
    try:
        redis_client.delete(_KEY_FAILURES)
    except Exception:
        pass
