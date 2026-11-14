from pathlib import Path

from app.database.connection import get_connection

def init_database() -> None:
    schema_path = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")

    with get_connection() as connection:
        connection.execute(schema)

        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()

    print("База данных успешно инициализирована")
    print("Таблицы:", ", ".join(table[0] for table in tables))


if __name__ == "__main__":
    init_database()
