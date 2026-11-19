from PyQt6.QtCore import QThread, pyqtSignal
import psycopg

from app.database.calculations import get_calculations, get_calculation_by_id


class CalculationsLoader(QThread):
    loaded = pyqtSignal(list)
    failed = pyqtSignal()

    def run(self) -> None:
        calculations = get_calculations(100)

        if calculations is None:
            self.failed.emit()
        else:
            self.loaded.emit(calculations)


class CalculationDetailsLoader(QThread):
    loaded = pyqtSignal(dict)
    failed = pyqtSignal()
    missing = pyqtSignal()

    def __init__(self, calculation_id: int, parent=None):
        super().__init__(parent)
        self.calculation_id = calculation_id

    def run(self) -> None:
        try:
            calculation = get_calculation_by_id(self.calculation_id)
        except psycopg.Error:
            self.failed.emit()
            return

        if calculation is None:
            self.missing.emit()
        else:
            self.loaded.emit(calculation)
