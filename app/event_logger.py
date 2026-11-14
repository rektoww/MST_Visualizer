import logging
from queue import Queue, Full
from threading import Thread

from app.database.event_logs import add_event
from app.database.calculations import add_calculation


logger = logging.getLogger(__name__)
events_queue = Queue(maxsize=500)
worker = None
STOP = object()

def process_events() -> None:
    while True:
        event = events_queue.get()

        try:
            if event is STOP:
                break

            kind, data = event

            if kind == "event":
                add_event(*data)

            elif kind == "calculation":
                calculation_id = add_calculation(**data)

                if calculation_id is not None:
                    add_event(
                        "INFO", "mst", "mst.saved", "MST calculation saved",
                        {"algorithm": data["algorithm"], "run_mode": data["run_mode"]},
                        calculation_id
                    )

        except Exception:
            logger.exception("Unexpected error while processing event")

        finally:
            events_queue.task_done()

def start_event_worker() -> None:
    global worker

    if worker is not None and worker.is_alive():
        return

    worker = Thread(target=process_events, name="DBEventWriter", daemon=True)
    worker.start()

def record_event(level: str, source: str, event_code: str, message: str, details: dict | None = None, calculation_id: int | None = None) -> None:
    level = level.upper()

    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ValueError(f"Unknown logging level: {level}")

    logging.getLogger(source).log(getattr(logging, level), "[%s] %s", event_code, message)
    start_event_worker()

    try:
        events_queue.put_nowait(("event", (level, source, event_code, message, details, calculation_id)))

    except Full:
        logger.warning("Database event queue is full: %s", event_code)

def queue_calculation(data: dict) -> None:
    start_event_worker()

    try:
        events_queue.put_nowait(("calculation", data))
    except Full:
        logger.warning("Database queue is full: calculation not saved")

def stop_event_worker() -> None:
    if worker is None or not worker.is_alive():
        return

    try:
        events_queue.put(STOP, timeout=0.1)

    except Full:
        logger.warning("Cannot stop database event worker: queue is full")
        return

    worker.join(timeout=2)

    if worker.is_alive():
        logger.warning("Some database events may not have been saved")
