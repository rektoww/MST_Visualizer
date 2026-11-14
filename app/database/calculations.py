import logging

import psycopg
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row

from app.database.connection import get_connection


logger = logging.getLogger(__name__)


def add_calculation(algorithm: str, run_mode: str, vertex_count: int, edge_count: int,
                    graph_data: dict, result_edges: list, steps: list,
                    total_weight: float, duration_ms: float) -> int | None:
    try:
        with get_connection() as connection:
            result = connection.execute(
                """INSERT INTO calculations
                   (algorithm, run_mode, vertex_count, edge_count, graph_data,
                    result_edges, steps, total_weight, duration_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (algorithm, run_mode, vertex_count, edge_count, Jsonb(graph_data),
                 Jsonb(result_edges), Jsonb(steps), total_weight, duration_ms)
            )
            calculation_id = result.fetchone()[0]

        logger.info("Calculation saved: id=%s, algorithm=%s, mode=%s", calculation_id, algorithm, run_mode)
        return calculation_id

    except psycopg.Error:
        logger.exception("Failed to save calculation: algorithm=%s", algorithm)
        return None

def get_calculations(limit: int = 100) -> list[dict] | None:
    limit = max(1, min(limit, 500))

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT id, created_at, algorithm, run_mode, vertex_count,
                              edge_count, total_weight, duration_ms
                       FROM calculations
                       ORDER BY created_at DESC, id DESC
                       LIMIT %s""",
                    (limit,)
                )
                return cursor.fetchall()

    except psycopg.Error:
        logger.exception("Failed to load calculations")
        return None


def get_calculation_by_id(calculation_id: int) -> dict | None:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT * FROM calculations WHERE id = %s", (calculation_id,))
                return cursor.fetchone()

    except psycopg.Error:
        logger.exception("Failed to load calculation: id=%s", calculation_id)
        return None
