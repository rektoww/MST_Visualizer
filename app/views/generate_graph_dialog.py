
from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QDialog, QMessageBox


class GenerateGraphDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        ui_path = Path(__file__).resolve().parents[2] / "ui" / "generate_graph_dialog.ui"
        uic.loadUi(str(ui_path), self)

        self.spinVertexCount.valueChanged.connect(self.update_edge_limits)
        self.btnCancelGenerate.clicked.connect(self.reject)
        self.btnConfirmGenerate.clicked.connect(self.confirm_generation)

        self.update_edge_limits(self.spinVertexCount.value())

    def update_edge_limits(self, vertex_count: int) -> None:
        minimum = vertex_count - 1
        maximum = vertex_count * (vertex_count - 1) // 2

        self.spinEdgeCount.setRange(minimum, maximum)

    def confirm_generation(self) -> None:
        if self.spinMinWeight.value() > self.spinMaxWeight.value():
            QMessageBox.warning(self, "Ошибка", "Минимальный вес больше максимального")
            return

        self.accept()
