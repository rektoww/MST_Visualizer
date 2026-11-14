from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QDialog, QMessageBox

from app.i18n import translate

class GenerateGraphDialog(QDialog):
    def __init__(self, parent=None, language: str = "ru") -> None:
        super().__init__(parent)
        self.language = language

        ui_path = Path(__file__).resolve().parents[2] / "ui" / "generate_graph_dialog.ui"
        uic.loadUi(str(ui_path), self)

        self.spinVertexCount.valueChanged.connect(self.update_edge_limits)
        self.btnCancelGenerate.clicked.connect(self.reject)
        self.btnConfirmGenerate.clicked.connect(self.confirm_generation)

        self.update_edge_limits(self.spinVertexCount.value())

        self.update_language(language)

    def update_edge_limits(self, vertex_count: int) -> None:
        minimum = vertex_count - 1
        maximum = vertex_count * (vertex_count - 1) // 2

        self.spinEdgeCount.setRange(minimum, maximum)

    def confirm_generation(self) -> None:
        if self.spinMinWeight.value() > self.spinMaxWeight.value():
            QMessageBox.warning(
                self,
                translate("error_title", self.language),
                translate("min_weight_greater_than_max", self.language)
            )
            return

        self.accept()

    def update_language(self, language: str) -> None:
        self.setWindowTitle(translate("generation_title", language))

        labels = [
            (self.labelIntroduction, "generation_intro"),
            (self.labelVertexCount, "vertex_count"),
            (self.labelEdgeCount, "edge_count"),
            (self.labelMinWeight, "min_weight"),
            (self.labelMaxWeight, "max_weight"),
            (self.labelConnected, "connected_hint"),
            (self.labelReplaceWarning, "replace_warning"),
            (self.btnCancelGenerate, "cancel"),
            (self.btnConfirmGenerate, "generate")
        ]

        for widget, key in labels:
            widget.setText(translate(key, language))

        self.spinEdgeCount.setToolTip(
            translate("edge_hint", language)
        )
