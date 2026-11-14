from PyQt6.QtCore import QThread, pyqtSignal

from app.database.event_logs import get_events


class EventLogsLoader(QThread):
    loaded = pyqtSignal(list)
    failed = pyqtSignal()

    def run(self) -> None:
        events = get_events(500)

        if events is None:
            self.failed.emit()
        else:
            self.loaded.emit(events)
