"""Postgres persistence layer for per-request cost rows."""

import psycopg

DEFAULT_MODEL = "gemini-2.5-flash"


def ensure_costs_table(postgres_url: str) -> None:
    """Create the request_costs table if it does not exist."""
    if not postgres_url:
        return
    with psycopg.connect(postgres_url) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_costs (
                id            SERIAL PRIMARY KEY,
                created_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
                input_tokens  INT            NOT NULL,
                output_tokens INT            NOT NULL,
                cost_usd      NUMERIC(12, 8) NOT NULL,
                cache_hit     BOOLEAN        NOT NULL,
                model         TEXT           NOT NULL
            )
        """)
        conn.commit()


def query_costs(postgres_url: str, days: int) -> dict:
    """Return aggregate cost stats for the given lookback window in days."""
    zero: dict = {
        "total_requests": 0,
        "cache_hits": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
    }
    if not postgres_url:
        return zero
    try:
        with psycopg.connect(postgres_url) as conn:
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*)                           AS total_requests,
                    COUNT(*) FILTER (WHERE cache_hit)  AS cache_hits,
                    COALESCE(SUM(input_tokens),  0)    AS total_input_tokens,
                    COALESCE(SUM(output_tokens), 0)    AS total_output_tokens,
                    COALESCE(SUM(cost_usd),      0)    AS total_cost_usd
                FROM request_costs
                WHERE created_at >= NOW() - INTERVAL '{days} days'
                """,
            ).fetchone()
        if row is None:
            return zero
        return {
            "total_requests":      int(row[0]),
            "cache_hits":          int(row[1]),
            "total_input_tokens":  int(row[2]),
            "total_output_tokens": int(row[3]),
            "total_cost_usd":      float(row[4]),
        }
    except Exception:
        return zero


def insert_cost(
    postgres_url: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    cache_hit: bool,
    model: str = DEFAULT_MODEL,
) -> None:
    """Insert one request_costs row; no-ops on empty URL or any error."""
    if not postgres_url:
        return
    try:
        with psycopg.connect(postgres_url) as conn:
            conn.execute(
                """
                INSERT INTO request_costs
                    (input_tokens, output_tokens, cost_usd, cache_hit, model)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (input_tokens, output_tokens, cost_usd, cache_hit, model),
            )
            conn.commit()
    except Exception:
        pass
