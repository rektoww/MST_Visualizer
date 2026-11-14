import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def get_connection() -> psycopg.Connection:
    load_dotenv(Path(__file__).parents[2] / ".env")

    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=5
    )