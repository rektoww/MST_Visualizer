import os
from pathlib import Path
from time import monotonic
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from app.database import calculations, event_logs, init_db
from app.database.connection import get_connection


SCHEMA = (Path(__file__).resolve().parents[1] / "sql/schema.sql").read_text(encoding="utf-8")
LEGACY_TABLES = SCHEMA.split("-- Apply the same constraints", 1)[0]


@pytest.fixture
def postgres_schema(monkeypatch):
    dsn = os.getenv("MST_TEST_POSTGRES")
    if not dsn:
        pytest.skip("MST_TEST_POSTGRES must point to a temporary PostgreSQL database")
    schema = "mst_test_" + uuid4().hex

    def connect(**kwargs):
        return psycopg.connect(dsn, options=f"-c search_path={schema}")

    monkeypatch.setattr(calculations, "get_connection", connect)
    monkeypatch.setattr(event_logs, "get_connection", connect)
    monkeypatch.setattr(init_db, "get_connection", connect)

    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield connect
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def catalog(connection):
    constraints = connection.execute(
        """SELECT conname, convalidated FROM pg_constraint
           WHERE conrelid IN ('calculations'::regclass, 'event_logs'::regclass)
             AND contype = 'c' ORDER BY conname"""
    ).fetchall()
    indexes = connection.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND indexname LIKE 'idx_%'"
    ).fetchall()
    return dict(constraints), {name for (name,) in indexes}


def save_calculation():
    graph_data = {"version": 1, "vertices": [{"id": 1, "x": 5.04, "y": 0}], "edges": []}
    return calculations.add_calculation("prim", "step", 1, 0, graph_data, [], [], 0.0, 0.125)


def test_postgres_fresh_schema_and_repository_round_trip(postgres_schema):
    with postgres_schema() as connection:
        connection.execute(SCHEMA)
        checks, indexes = catalog(connection)
        assert len(checks) == 9 and all(checks.values())
        assert indexes == {"idx_calculations_created_at", "idx_event_logs_created_at",
                           "idx_event_logs_calculation_id"}

    calculation_id = save_calculation()
    assert calculation_id is not None
    assert event_logs.add_event("INFO", "test", "test.saved", "saved",
                                {"mode": "step"}, calculation_id) is not None
    record = calculations.get_calculation_by_id(calculation_id)
    assert record["graph_data"]["vertices"][0]["x"] == 5.04
    assert calculations.decode_calculation(record)[2].total_weight == 0
    assert calculations.get_calculations()[0]["id"] == calculation_id
    assert calculations.get_calculation_by_id(calculation_id + 1) is None
    event = event_logs.get_events()[0]
    assert event["calculation_id"] == calculation_id
    assert event["details"] == {"mode": "step"}


def test_postgres_migration_is_repeatable_and_preserves_conflicts(postgres_schema, capsys):
    with postgres_schema() as connection:
        connection.execute(LEGACY_TABLES)
        assert catalog(connection) == ({}, set())

    valid_id = save_calculation()
    with postgres_schema() as connection:
        conflict_id = connection.execute(
            """INSERT INTO calculations (algorithm, run_mode, vertex_count, edge_count, graph_data,
                                         result_edges, steps, total_weight, duration_ms)
               SELECT 'legacy', run_mode, vertex_count, edge_count, graph_data,
                      result_edges, steps, total_weight, duration_ms FROM calculations WHERE id = %s
               RETURNING id""", (valid_id,)
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO event_logs (level, source, event_code, message, calculation_id) "
            "VALUES ('INFO', 'test', 'legacy', 'keep me', %s)", (conflict_id,)
        )

    for _ in range(2):
        assert init_db.init_database() is False
        assert "calculations_algorithm_check" in capsys.readouterr().out
        with postgres_schema() as connection:
            checks, indexes = catalog(connection)
            assert len(checks) == 9 and list(checks.values()).count(False) == 1
            assert len(indexes) == 3
            assert connection.execute("SELECT count(*) FROM calculations").fetchone() == (2,)
            assert connection.execute("SELECT calculation_id FROM event_logs").fetchone() == (conflict_id,)

    with pytest.raises(psycopg.errors.CheckViolation):
        with postgres_schema() as connection:
            connection.execute("UPDATE calculations SET algorithm = 'wrong' WHERE id = %s", (valid_id,))
    with pytest.raises(psycopg.errors.CheckViolation):
        with postgres_schema() as connection:
            connection.execute("UPDATE calculations SET total_weight = 'NaN' WHERE id = %s", (valid_id,))


def test_postgres_client_deadline_closes_stalled_connection(postgres_schema, monkeypatch):
    params = conninfo_to_dict(os.environ["MST_TEST_POSTGRES"])
    for key, param in (("DB_HOST", "host"), ("DB_PORT", "port"), ("DB_NAME", "dbname"),
                       ("DB_USER", "user"), ("DB_PASSWORD", "password")):
        monkeypatch.setenv(key, params.get(param, ""))
    with get_connection(operation_timeout=0.2) as connection:
        started = monotonic()
        with pytest.raises(psycopg.OperationalError):
            connection.execute("SELECT pg_sleep(2)")
        assert monotonic() - started < 1.5
        assert connection.closed
