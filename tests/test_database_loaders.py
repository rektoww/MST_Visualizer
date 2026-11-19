import psycopg

from app.views.calculations_loader import CalculationsLoader, CalculationDetailsLoader
from app.views.event_logs_loader import EventLogsLoader


def test_calculations_loader_success(monkeypatch):
    records = [{"id": 1}, {"id": 2}]
    received = []

    monkeypatch.setattr("app.views.calculations_loader.get_calculations", lambda limit: records)

    loader = CalculationsLoader()
    loader.loaded.connect(received.append)
    loader.run()

    assert received == [records]


def test_calculations_loader_failure(monkeypatch):
    failed = []

    monkeypatch.setattr("app.views.calculations_loader.get_calculations", lambda limit: None)

    loader = CalculationsLoader()
    loader.failed.connect(lambda: failed.append(True))
    loader.run()

    assert failed == [True]


def test_calculation_details_loader_success(monkeypatch):
    calculation = {"id": 5, "algorithm": "prim", "total_weight": 49.19}
    received = []
    requested_ids = []

    def fake_get_calculation(calculation_id):
        requested_ids.append(calculation_id)
        return calculation

    monkeypatch.setattr("app.views.calculations_loader.get_calculation_by_id", fake_get_calculation)

    loader = CalculationDetailsLoader(5)
    loader.loaded.connect(received.append)
    loader.run()

    assert requested_ids == [5]
    assert received == [calculation]


def test_calculation_details_loader_failure(monkeypatch):
    failed = []

    def failed_query(calculation_id):
        raise psycopg.OperationalError("offline")

    monkeypatch.setattr("app.views.calculations_loader.get_calculation_by_id", failed_query)

    loader = CalculationDetailsLoader(999)
    loader.failed.connect(lambda: failed.append(True))
    loader.run()

    assert failed == [True]


def test_calculation_details_loader_not_found(monkeypatch):
    outcomes = []
    monkeypatch.setattr("app.views.calculations_loader.get_calculation_by_id", lambda calculation_id: None)
    loader = CalculationDetailsLoader(999)
    loader.missing.connect(lambda: outcomes.append("missing"))
    loader.failed.connect(lambda: outcomes.append("failed"))

    loader.run()

    assert outcomes == ["missing"]


def test_event_logs_loader_success(monkeypatch):
    events = [
        {"id": 1, "level": "INFO"},
        {"id": 2, "level": "WARNING"}
    ]
    received = []

    monkeypatch.setattr("app.views.event_logs_loader.get_events", lambda limit: events)

    loader = EventLogsLoader()
    loader.loaded.connect(received.append)
    loader.run()

    assert received == [events]


def test_event_logs_loader_failure(monkeypatch):
    failed = []

    monkeypatch.setattr("app.views.event_logs_loader.get_events", lambda limit: None)

    loader = EventLogsLoader()
    loader.failed.connect(lambda: failed.append(True))
    loader.run()

    assert failed == [True]
