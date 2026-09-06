# src/margin_checker/db.py

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import psycopg
from dotenv import load_dotenv

load_dotenv()

DB_CONN = os.getenv("DB_CONN")
HISTORY_LIMIT = 10
DEFAULT_DISPLAY_TZ = "Europe/Berlin"


def connect():
    if not DB_CONN:
        raise RuntimeError(
            "DB_CONN is not set. Copy .env.example to .env and configure it."
        )
    return psycopg.connect(DB_CONN)


def display_timezone():
    name = (
        os.getenv("DISPLAY_TZ")
        or os.getenv("TZ")
        or DEFAULT_DISPLAY_TZ
    )
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_DISPLAY_TZ)


def format_created_at(created_at):
    """Format a query_logs timestamp in the local display timezone."""
    if created_at is None:
        return ""
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(display_timezone()).strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------
# Contract data
# --------------------------------------------------

def load_contract_chunks():
    """Load contract chunks from PostgreSQL."""

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT contract_id, chunk_text
            FROM contract_chunks
            """
        ).fetchall()

    return [
        {
            "contract_id": row[0],
            "chunk_text": row[1]
        }
        for row in rows
    ]


# --------------------------------------------------
# Monitoring table
# --------------------------------------------------

def init_monitoring_table():
    """Create the query log table if it does not exist."""

    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS query_logs (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                question TEXT NOT NULL,
                answer TEXT,
                route TEXT,
                response_time REAL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost REAL,
                relevance TEXT,
                relevance_explanation TEXT,
                feedback INTEGER
            )
            """
        )
        column_type = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'query_logs'
              AND column_name = 'created_at'
            """
        ).fetchone()
        if column_type and column_type[0] == "timestamp without time zone":
            conn.execute(
                """
                ALTER TABLE query_logs
                ALTER COLUMN created_at TYPE TIMESTAMPTZ
                USING created_at AT TIME ZONE 'UTC'
                """
            )
        conn.commit()


# --------------------------------------------------
# Save query
# --------------------------------------------------

def save_query_log(
    question,
    answer,
    route,
    response_time,
    prompt_tokens,
    completion_tokens,
    total_tokens,
    cost,
    relevance,
    relevance_explanation
):
    """Save one RAG request for monitoring."""

    with connect() as conn:

        row = conn.execute(
            """
            INSERT INTO query_logs (
                question,
                answer,
                route,
                response_time,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cost,
                relevance,
                relevance_explanation
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                question,
                answer,
                route,
                response_time,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cost,
                relevance,
                relevance_explanation
            )
        ).fetchone()

        conn.commit()

    return row[0]


# --------------------------------------------------
# Save feedback
# --------------------------------------------------

def save_feedback(log_id, feedback):
    """Save user feedback for a query."""

    with connect() as conn:

        conn.execute(
            """
            UPDATE query_logs
            SET feedback = %s
            WHERE id = %s
            """,
            (feedback, log_id)
        )

        conn.commit()


# --------------------------------------------------
# Query history
# --------------------------------------------------

def load_query_history(limit=HISTORY_LIMIT):
    """Load recent questions and answers."""

    with connect() as conn:

        rows = conn.execute(
            """
            SELECT id, created_at, question, answer
            FROM query_logs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,)
        ).fetchall()

    return rows


def delete_query_log(log_id):
    """Delete one history row."""

    with connect() as conn:
        conn.execute(
            "DELETE FROM query_logs WHERE id = %s",
            (log_id,)
        )
        conn.commit()


def delete_all_query_logs():
    """Delete the visible query history."""

    with connect() as conn:
        conn.execute("DELETE FROM query_logs")
        conn.commit()


# --------------------------------------------------
# Run directly
# --------------------------------------------------

if __name__ == "__main__":
    init_monitoring_table()
    print("Monitoring table created.")