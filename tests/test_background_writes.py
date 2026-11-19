from itertools import count
from queue import PriorityQueue
from threading import Event, Timer

import psycopg
import pytest

import app.event_logger as writer


@pytest.fixture
def isolated_writer(monkeypatch):
    monkeypatch.setattr(writer, "worker", None)
    monkeypatch.setattr(writer, "stopping", Event())
    monkeypatch.setattr(writer, "sequence", count())
    monkeypatch.setattr(writer, "events_queue", PriorityQueue(maxsize=1))
    monkeypatch.setattr(writer, "add_event", lambda *args: 1)
    yield
    assert writer.stop_event_worker(timeout=2)


def test_overflow_is_reported_and_shutdown_finishes_accepted_work(isolated_writer, monkeypatch):
    started, release = Event(), Event()
    modes = []

    def slow_write(algorithm, run_mode):
        modes.append(run_mode)
        started.set()
        assert release.wait(2)
        return len(modes)

    monkeypatch.setattr(writer, "add_calculation", slow_write)
    first = writer.queue_calculation(dict(algorithm="prim", run_mode="build"))
    try:
        assert started.wait(1)
        second = writer.queue_calculation(dict(algorithm="prim", run_mode="step"))
        rejected = writer.queue_calculation(dict(algorithm="prim", run_mode="build"))
        assert rejected.result(timeout=0) is False
        assert not first.done()
        assert not second.done()
        Timer(0.05, release.set).start()
        assert writer.stop_event_worker(timeout=2)
        assert first.result(timeout=0) is True
        assert second.result(timeout=0) is True
        assert modes == ["build", "step"]
    finally:
        release.set()


def test_database_error_is_reported_without_retry(isolated_writer, monkeypatch):
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise psycopg.OperationalError("disconnected")

    monkeypatch.setattr(writer, "add_calculation", fail)
    data = dict(algorithm="kruskal", run_mode="step")
    result = writer.queue_calculation(data)
    assert result.result(timeout=1) is False
    assert calls == [data]


def test_expired_pending_calculation_is_not_written(isolated_writer, monkeypatch):
    started, release = Event(), Event()
    calls = []

    def write(**kwargs):
        calls.append(kwargs)
        started.set()
        assert release.wait(2)
        return 1

    monkeypatch.setattr(writer, "add_calculation", write)
    first = writer.queue_calculation(dict(algorithm="prim", run_mode="step"))
    try:
        assert started.wait(1)
        queued = writer.queue_calculation(dict(algorithm="prim", run_mode="build"))
        assert queued.cancel()
        assert writer.stop_event_worker(timeout=0) is False
    finally:
        release.set()

    assert first.result(timeout=1) is True
    assert writer.stop_event_worker(timeout=2)
    assert len(calls) == 1
