from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QStatusBar, QInputDialog, QMessageBox, QGraphicsView
from PyQt6.QtCore import Qt, QPointF, QEvent

from app.core.graph import Graph
from app.views.graph_scene import GraphScene
from app.core.exceptions import GraphError

from app.core.algorithms.kruskal import kruskal
from app.core.algorithms.prim import prim


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        ui_path = (Path(__file__).resolve().parents[2] / "ui" / "main_window.ui")

        uic.loadUi(str(ui_path), self)

        self.graph = Graph()

        self.graph_scene = GraphScene(self)
        self.graph_scene.setSceneRect(0, 0, 1200, 900)

        self.graphView.setScene(self.graph_scene)
        self.graphView.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.graphView.viewport().installEventFilter(self)
        self.graphView.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self.pending_vertex: int | None = None

        self.btnBuildMst.setEnabled(False)
        self.btnStepMode.setEnabled(False)
        self.btnGenerateGraph.setEnabled(False)

        self.comboAlgorithm.currentTextChanged.connect(self.on_algorithm_changed)
        self.graph_scene.vertex_clicked.connect(self.on_vertex_clicked)
        self.graph_scene.empty_space_clicked.connect(self.add_vertex_at)
        self.btnClearCanvas.clicked.connect(self.clear_canvas)

        self.last_result = None

        self.btnBuildMst.setEnabled(True)
        self.btnShowOriginalGraph.setEnabled(False)

        self.btnBuildMst.clicked.connect(self.build_mst)
        self.btnShowOriginalGraph.clicked.connect(self.show_original_graph)

        self.statusBar().showMessage("Готово к работе")

    def on_algorithm_changed(self, algorithm: str) -> None:
        self.statusBar().showMessage(f"Выбран: {algorithm}")

    def add_vertex_at(self, pos: QPointF) -> None:
        if not self.graph_scene.can_place_vertex(pos):
            self.statusBar().showMessage("Слишком близко к другой вершине")
            return

        self.invalidate_mst()

        vertex_id = max(self.graph.vertices, default=0) + 1

        self.graph.add_vertex(vertex_id)
        self.graph_scene.add_vertex(vertex_id, pos)

        self.statusBar().showMessage(f"Добавлена вершина {vertex_id}")

    def on_vertex_clicked(self, vertex_id: int) -> None:
        if self.pending_vertex is None:
            self.pending_vertex = vertex_id
            self.graph_scene.select_vertex(vertex_id)
            self.statusBar().showMessage(f"Выбрана вершина {vertex_id}. Выберите вторую")
            return

        first = self.pending_vertex
        self.pending_vertex = None
        self.graph_scene.select_vertex(None)

        if first == vertex_id:
            self.statusBar().showMessage("Выбор вершины отменён")
            return

        if self.graph.has_edge(first, vertex_id):
            QMessageBox.warning(
                self, "Ребро уже существует",
                f"Вершины {first} и {vertex_id} уже соединены"
            )
            return

        weight, ok = QInputDialog.getDouble(
            self, "Вес ребра", f"Вес ребра {first}–{vertex_id}:",
            1.0, -1000000.0, 1000000.0, 2
        )

        if not ok:
            self.statusBar().showMessage("Добавление ребра отменено")
            return

        try:
            self.graph.add_edge(first, vertex_id, weight)
        except GraphError as error:
            QMessageBox.warning(self, "Ошибка добавления ребра", str(error))
            return

        self.invalidate_mst()
        self.graph_scene.add_edge(first, vertex_id, weight)
        self.statusBar().showMessage(f"Добавлено ребро {first}–{vertex_id}, вес {weight:g}")

    def eventFilter(self, watched, event) -> bool:
        if watched is self.graphView.viewport() and event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()

                if delta:
                    factor = 1.15 ** (delta / 120)
                else:
                    factor = 1.002 ** event.pixelDelta().y()

                current_scale = self.graphView.transform().m11()

                if 0.4 <= current_scale * factor <= 3.0:
                    self.graphView.scale(factor, factor)

                return True

        return super().eventFilter(watched, event)

    def clear_canvas(self) -> None:
        if not self.graph.vertices:
            self.statusBar().showMessage("Полотно уже пустое")
            return

        answer = QMessageBox.question(
            self, "Очистка полотна",
            "Удалить все вершины и рёбра?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.graph = Graph()
        self.graph_scene.clear_graph()
        self.pending_vertex = None
        self.graphView.resetTransform()

        self.last_result = None
        self.btnShowOriginalGraph.setEnabled(False)

        self.statusBar().showMessage("Полотно очищено")

    def build_mst(self) -> None:
        algorithm_index = self.comboAlgorithm.currentIndex()

        if algorithm_index not in (0, 1):
            QMessageBox.warning(self, "Алгоритм не выбран", "Сначала выберите алгоритм")
            return

        try:
            if algorithm_index == 0:
                result = kruskal(self.graph)
            else:
                result = prim(self.graph)
        except GraphError as error:
            QMessageBox.warning(self, "Построение остова", str(error))
            return

        self.last_result = result
        self.graph_scene.show_mst(result.edges)
        self.btnShowOriginalGraph.setEnabled(True)

        self.statusBar().showMessage(
            f"Остов построен. Рёбер: {len(result.edges)}, общий вес: {result.total_weight:g}"
        )

    def show_original_graph(self) -> None:
        self.graph_scene.show_original_graph()
        self.btnShowOriginalGraph.setEnabled(False)
        self.statusBar().showMessage("Показан исходный граф")

    def invalidate_mst(self) -> None:
        self.last_result = None
        self.graph_scene.show_original_graph()
        self.btnShowOriginalGraph.setEnabled(False)