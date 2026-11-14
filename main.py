import sys

from PyQt6.QtWidgets import QApplication
from app.views.main_window import MainWindow
from app.logging_config import setup_logging
from app.event_logger import record_event, stop_event_worker

def main():
    setup_logging()

    app = QApplication(sys.argv)

    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    record_event("INFO", "app", "app.started", "MST Visualizer started")

    exit_code = app.exec()

    if window.history_loader is not None:
        window.history_loader.wait()

    if window.calculation_loader is not None:
        window.calculation_loader.wait()

    if window.events_loader is not None:
        window.events_loader.wait()

    record_event("INFO", "app", "app.stopped", "MST Visualizer stopped")
    stop_event_worker()
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
