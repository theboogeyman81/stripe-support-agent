# Spec 50 — Circuit Breaker

## Feature
Track consecutive failures to the primary Gemini model and, after a threshold is
reached, stop trying the primary model for a cooldown window. This prevents a
struggling primary from slowing down every request with a failed call before
falling back. After the cooldown, the circuit resets automatically and the primary
is tried again.

The circuit breaker is implemented as a thin Redis-backed module. If Redis is
unavailable, the circuit breaker is silently skipped — fail open.

## Why
Feature 49 (fallback chain) added resilience for individual failures, but still
pays the latency cost of a failing primary call on every request. If the primary
is down for minutes, every user waits for a timeout before getting the secondary.
The circuit breaker short-circuits that wait: after 3 consecutive primary failures,
the primary is skipped entirely for 60 seconds.

## Input contract
- `redis_client: redis.Redis | None` — from `request.app.state.redis_client`.
- Failure/success events fired by `generate()` in `src/rag/generator.py`.

## Output contract
- `is_circuit_open(redis_client) -> bool` — `True` means skip primary.
- Side-effect functions `record_failure` and `record_success` return `None`.

## Scope (in)
- `src/rag/circuit_breaker.py` — three public functions:
  - `is_circuit_open(redis_client: redis.Redis | None) -> bool`
  - `record_failure(redis_client: redis.Redis | None) -> None`
  - `record_success(redis_client: redis.Redis | None) -> None`
  - Constants: `FAILURE_THRESHOLD = 3`, `COOLDOWN_SECONDS = 60`
  - Redis keys: `"cb:open"` (flag, expires after cooldown), `"cb:failures"` (counter)
- `src/rag/generator.py` — integrate circuit breaker into the fallback loop:
  - Before the loop: if `is_circuit_open(redis_client)`, start at level 1 (skip primary).
  - On primary success (level 0): call `record_success(redis_client)`.
  - On primary failure (level 0): call `record_failure(redis_client)`.
  - No change to secondary or apology paths.
- `tests/test_circuit_breaker.py` — unit tests, Redis mocked.

## Scope (out)
- No "half-open" state — TTL expiry on `cb:open` is sufficient; when the key
  expires, the next request tries the primary again naturally.
- No Langfuse event — plain `print` at WARNING level.
- No admin endpoint to manually reset the circuit (out of scope for this feature).
- No change to `/chat` route or guardrails.

## Dependencies
- New: none — `redis` already installed.
- Existing: `src/rag/generator.py`, Redis client from app state.

## Acceptance criteria
1. `uv run pytest tests/test_circuit_breaker.py -v` — all tests pass.
2. Unit test: `record_failure` called 3 times → `is_circuit_open` returns `True`.
3. Unit test: `is_circuit_open` returns `False` when `cb:open` key absent.
4. Unit test: `record_success` clears the failure counter → after success, failure
   count resets to 0.
5. Unit test: `is_circuit_open` returns `False` when `redis_client=None`.
6. `uv run ruff check src/rag/circuit_breaker.py src/rag/generator.py tests/test_circuit_breaker.py` passes.
7. `uv run pytest tests/test_generator.py tests/test_generator_fallback.py -v` — all existing tests still pass.

## Failure modes to handle
- **No Redis**: all three functions return `False`/`None` immediately — no error.
- **Redis error during check**: catch exception, return `False` (fail open — better
  to try the primary than to skip it due to a Redis glitch).
- **Cooldown expiry**: `cb:open` key expires naturally via TTL; no explicit reset
  needed.

## Notes

### Redis key design
| Key | Type | Value | TTL |
|---|---|---|---|
| `cb:failures` | string (int) | consecutive failure count | none (cleared on success) |
| `cb:open` | string | `"1"` | `COOLDOWN_SECONDS` (60 s) |

### `record_failure` algorithm
1. If `redis_client is None`: return.
2. Increment `cb:failures` (INCR).
3. If new count >= `FAILURE_THRESHOLD`: set `cb:open = "1"` with TTL `COOLDOWN_SECONDS`.
   Print `[WARNING] Circuit breaker opened — skipping primary for 60s`.

### `record_success` algorithm
1. If `redis_client is None`: return.
2. Delete `cb:failures` (reset counter).
3. Do NOT delete `cb:open` — let the cooldown expire naturally. A single success
   while the circuit is open does not immediately close it; the TTL does.

### Updated fallback loop in `generate()`
```python
start_level = 1 if is_circuit_open(redis_client) else 0
models = [GEMINI_MODEL_PRIMARY, GEMINI_MODEL_SECONDARY]

for level, model in enumerate(models[start_level:], start=start_level):
    try:
        result = _call_model(model, prompt, settings)
        if level == 0:
            record_success(redis_client)
        result["cache_hit"] = False
        result["fallback_level"] = level
        if key is not None:
            set_cached(redis_client, key, result, cache_ttl)
        return result
    except Exception as exc:
        print(f"[WARNING] Gemini model {model} failed: {exc}")
        if level == 0:
            record_failure(redis_client)
```

### Why not track failures in memory?
In-process state is lost on restart and doesn't work across multiple worker
processes. Redis is already available and purpose-built for this shared ephemeral
state. The overhead is two Redis calls per primary failure — negligible.
