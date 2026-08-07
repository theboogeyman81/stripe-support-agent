"""Postgres persistence layer for support tickets."""

import psycopg


def ensure_tickets_table(postgres_url: str) -> None:
    """Create the tickets table if it does not exist."""
    with psycopg.connect(postgres_url) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id         SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                category   TEXT NOT NULL,
                summary    TEXT NOT NULL
            )
        """)
        conn.commit()


def insert_ticket(postgres_url: str, category: str, summary: str) -> int:
    """Insert one ticket row and return the new ticket id."""
    ensure_tickets_table(postgres_url)
    with psycopg.connect(postgres_url) as conn:
        row = conn.execute(
            "INSERT INTO tickets (category, summary) VALUES (%s, %s) RETURNING id",
            (category, summary),
        ).fetchone()
        conn.commit()
    return row[0]
