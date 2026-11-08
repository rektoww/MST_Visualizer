from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QStatusBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        ui_path = (Path(__file__).resolve().parents[2] / "ui" / "main_window.ui")

        uic.loadUi(str(ui_path), self)

        self.btnBuildMst.setEnabled(False)
        self.btnStepMode.setEnabled(False)
        self.btnGenerateGraph.setEnabled(False)

        self.comboAlgorithm.currentTextChanged.connect(self.on_algorithm_changed)

        self.statusBar().showMessage("Готово к работе")

    def on_algorithm_changed(self, algorithm: str) -> None:
        self.statusBar().showMessage(f"Выбран: {algorithm}")
