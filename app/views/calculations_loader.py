from PyQt6.QtCore import QThread, pyqtSignal

from app.database.calculations import get_calculations


class CalculationsLoader(QThread):
    loaded = pyqtSignal(list)
    failed = pyqtSignal()

    def run(self) -> None:
        calculations = get_calculations(100)

        if calculations is None:
            self.failed.emit()
        else:
            self.loaded.emit(calculations)
