"""Redis-backed lifetime token and cost accumulators."""

import redis

STATS_INPUT_TOKENS  = "stats:input_tokens"
STATS_OUTPUT_TOKENS = "stats:output_tokens"
STATS_COST_MICROS   = "stats:cost_micros"   # cost_usd × 1_000_000 as int
STATS_REQUESTS      = "stats:requests"


def accumulate(
    redis_client: redis.Redis | None,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    """Add one request's token counts to the lifetime Redis totals."""
    if redis_client is None:
        return
    try:
        redis_client.incrby(STATS_INPUT_TOKENS, input_tokens)
        redis_client.incrby(STATS_OUTPUT_TOKENS, output_tokens)
        redis_client.incrby(STATS_COST_MICROS, int(round(cost_usd * 1_000_000)))
        redis_client.incr(STATS_REQUESTS)
    except Exception:
        pass


def get_token_stats(redis_client: redis.Redis | None) -> dict:
    """Return lifetime token/cost totals; all zeros if Redis unavailable."""
    zero: dict = {
        "total_input": 0,
        "total_output": 0,
        "total_cost_usd": 0.0,
        "total_requests": 0,
    }
    if redis_client is None:
        return zero
    try:
        inp  = int(redis_client.get(STATS_INPUT_TOKENS)  or 0)
        out  = int(redis_client.get(STATS_OUTPUT_TOKENS) or 0)
        mics = int(redis_client.get(STATS_COST_MICROS)   or 0)
        reqs = int(redis_client.get(STATS_REQUESTS)      or 0)
        return {
            "total_input": inp,
            "total_output": out,
            "total_cost_usd": mics / 1_000_000,
            "total_requests": reqs,
        }
    except Exception:
        return zero
