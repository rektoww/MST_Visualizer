from pathlib import Path

from app.database.connection import get_connection

def init_database() -> bool:
    schema_path = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")

    with get_connection(operation_timeout=None) as connection:
        connection.execute(schema)

        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()
        conflicts = connection.execute(
            """SELECT conrelid::regclass::text, conname
               FROM pg_constraint
               WHERE conrelid IN ('calculations'::regclass, 'event_logs'::regclass)
                 AND contype = 'c' AND NOT convalidated
               ORDER BY conname"""
        ).fetchall()

    if conflicts:
        print("Схема обновлена. Старые строки сохранены, но нарушают ограничения:")
        for table, constraint in conflicts:
            print(f"  {table}: {constraint}")
        return False

    print("База данных успешно инициализирована")
    print("Таблицы:", ", ".join(table[0] for table in tables))
    return True


if __name__ == "__main__":
    raise SystemExit(0 if init_database() else 1)
