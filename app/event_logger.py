import logging
from concurrent.futures import Future
from itertools import count
from queue import Empty, Full, PriorityQueue
from threading import Event, Lock, Thread

from app.database.calculations import add_calculation
from app.database.event_logs import add_event


logger = logging.getLogger(__name__)
events_queue = PriorityQueue(maxsize=500)
sequence = count()
stopping = Event()
worker_lock = Lock()
worker = None


def process_events() -> None:
    while not stopping.is_set() or not events_queue.empty():
        try:
            _, _, kind, data, result = events_queue.get(timeout=0.1)
        except Empty:
            continue

        try:
            if kind == "event":
                add_event(*data)
            elif result.set_running_or_notify_cancel():
                calculation_id = add_calculation(**data)
                result.set_result(calculation_id is not None)
                if calculation_id is not None:
                    record_event(
                        "INFO", "mst", "mst.saved", "MST calculation saved",
                        {"algorithm": data["algorithm"], "run_mode": data["run_mode"]},
                        calculation_id,
                    )
        except Exception:
            logger.exception("Unexpected database writer error")
            if result is not None and not result.done():
                result.set_result(False)
        finally:
            events_queue.task_done()


def enqueue(priority: int, kind: str, data, result: Future | None = None) -> bool:
    global worker

    with worker_lock:
        if stopping.is_set():
            return False
        try:
            events_queue.put_nowait((priority, next(sequence), kind, data, result))
        except Full:
            return False

        if worker is None or not worker.is_alive():
            worker = Thread(target=process_events, name="DBEventWriter", daemon=True)
            worker.start()
        return True


def record_event(level: str, source: str, event_code: str, message: str,
                 details: dict | None = None, calculation_id: int | None = None) -> None:
    level = level.upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ValueError(f"Unknown logging level: {level}")

    logging.getLogger(source).log(getattr(logging, level), "[%s] %s", event_code, message)
    if not enqueue(1, "event", (level, source, event_code, message, details, calculation_id)):
        logger.warning("Database event was not queued: %s", event_code)


def queue_calculation(data: dict) -> Future[bool]:
    result = Future()
    if not enqueue(0, "calculation", data, result):
        logger.warning("Database calculation was not queued")
        result.set_result(False)
    return result


def stop_event_worker(timeout: float = 2.0) -> bool:
    with worker_lock:
        stopping.set()
        current_worker = worker

    if current_worker is None:
        return True

    current_worker.join(timeout=timeout)
    if current_worker.is_alive():
        logger.warning("Database writer shutdown deadline expired")
        return False
    return True
