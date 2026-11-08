from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QStatusBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        ui_path = (Path(__file__).resolve().parents[2] / "ui" / "main_window.ui")

        uic.loadUi(str(ui_path), self)
        self.statusBar().showMessage("Готово к работе")

