import os
from pathlib import Path
from time import monotonic

import psycopg
from dotenv import load_dotenv


class TimedConnection(psycopg.Connection):
    deadline: float | None = None

    def wait(self, gen, interval=0.1, timeout=None):
        if self.deadline is None:
            return super().wait(gen, interval=interval, timeout=timeout)

        remaining = max(0, self.deadline - monotonic())
        if timeout is not None:
            remaining = min(remaining, timeout)
        try:
            return super().wait(gen, interval=interval, timeout=remaining)
        except psycopg.OperationalError:
            # A timed-out connection may still have a command in progress.
            self.close()
            raise


def get_connection(*, operation_timeout: float | None = 4.0) -> psycopg.Connection:
    load_dotenv(Path(__file__).parents[2] / ".env")

    connection = TimedConnection.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=2,
        options="-c statement_timeout=3000" if operation_timeout is not None else "-c lock_timeout=5000",
    )
    if operation_timeout is not None:
        connection.deadline = monotonic() + operation_timeout
    return connection
