import logging

import psycopg
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row

from app.database.connection import get_connection

logger = logging.getLogger(__name__)

def add_event(level: str, source: str, event_code: str, message: str, details: dict | None = None, calculation_id: int | None = None) -> int | None:
    try:
        with get_connection() as connection:
            result = connection.execute(
                """INSERT INTO event_logs (level, source, event_code, message, details, calculation_id)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (level, source, event_code, message, Jsonb(details or {}), calculation_id)
            )
            event_id = result.fetchone()[0]

        logger.info("Database event saved: id=%s, code=%s", event_id, event_code)
        return event_id

    except psycopg.Error:
        logger.exception("Failed to save database event: %s", event_code)
        return None

def get_events(limit: int = 100) -> list[dict] | None:
    limit = max(1, min(limit, 500))

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT * FROM event_logs ORDER BY created_at DESC, id DESC LIMIT %s", (limit,))
                return cursor.fetchall()

    except psycopg.Error:
        logger.exception("Failed to load database events")
        return None
