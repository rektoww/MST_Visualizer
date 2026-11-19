import signal
import sys

def main():
    shutdown_requested = False

    def request_shutdown(_signum, _frame):
        nonlocal shutdown_requested
        shutdown_requested = True

    previous_handlers = {sig: signal.signal(sig, request_shutdown) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        return run_application(lambda: shutdown_requested)
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def run_application(shutdown_requested) -> int:
    # Install the process handlers before loading Qt and the database driver.
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from app.event_logger import record_event, stop_event_worker
    from app.logging_config import setup_logging
    from app.views.main_window import MainWindow

    setup_logging()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()

    def check_signals():
        if shutdown_requested():
            signal_timer.stop()
            window.request_shutdown()

    signal_timer = QTimer(app, interval=100)
    signal_timer.timeout.connect(check_signals)
    signal_timer.start()
    window.show()
    record_event("INFO", "app", "app.started", "MST Visualizer started")

    try:
        return app.exec()
    finally:
        signal_timer.stop()
        record_event("INFO", "app", "app.stopped", "MST Visualizer stopped")
        stop_event_worker()

if __name__ == "__main__":
    sys.exit(main())
