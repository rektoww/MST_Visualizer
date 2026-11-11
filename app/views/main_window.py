from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QInputDialog, QMessageBox, QGraphicsView, QMenu
from PyQt6.QtCore import Qt, QPointF, QEvent, QTimer, QPoint
from PyQt6.QtGui import QShortcut, QKeySequence

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

        self.graph_scene.vertex_move_started.connect(self.begin_vertex_move)
        self.graph_scene.vertex_moved.connect(
            lambda vertex_id: self.statusBar().showMessage(f"Вершина {vertex_id} перемещена")
        )

        self.graphView.setScene(self.graph_scene)
        self.graphView.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.graphView.viewport().installEventFilter(self)
        self.graphView.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self.pending_vertex: int | None = None

        self.btnBuildMst.setEnabled(False)
        self.btnStepMode.setEnabled(True)
        self.btnGenerateGraph.setEnabled(False)

        self.comboAlgorithm.currentTextChanged.connect(self.on_algorithm_changed)
        self.graph_scene.vertex_clicked.connect(self.on_vertex_clicked)
        self.graph_scene.empty_space_clicked.connect(self.add_vertex_at)
        self.btnClearCanvas.clicked.connect(self.clear_canvas)

        self.last_result = None

        self.step_index: int | None = None

        self.btnPreviousStep.setEnabled(False)
        self.btnNextStep.setEnabled(False)

        self.btnStepMode.clicked.connect(self.start_step_mode)
        self.btnPreviousStep.clicked.connect(self.previous_step)
        self.btnNextStep.clicked.connect(self.next_step)
        self.graph_scene.vertex_context_requested.connect(self.show_vertex_menu)
        self.graph_scene.edge_context_requested.connect(self.show_edge_menu)

        self.btnBuildMst.setEnabled(True)
        self.btnShowOriginalGraph.setEnabled(False)

        self.btnBuildMst.clicked.connect(self.build_mst)
        self.btnShowOriginalGraph.clicked.connect(self.show_original_graph)

        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(1000)
        self.playback_timer.timeout.connect(self.advance_playback)

        self.decision_timer = QTimer(self)
        self.decision_timer.setSingleShot(True)
        self.decision_timer.timeout.connect(self.finish_step_preview)

        self.progressSteps.setVisible(False)

        self.btnPlayPause.setEnabled(False)
        self.btnPlayPause.clicked.connect(self.toggle_playback)

        self.comboPlaybackSpeed.setCurrentIndex(1)
        self.comboPlaybackSpeed.currentIndexChanged.connect(self.change_playback_speed)

        self._undo_stack = []

        self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.undo_shortcut.activated.connect(self.undo)

        self.statusBar().showMessage("Готово к работе")

    def on_algorithm_changed(self, algorithm: str) -> None:
        self.invalidate_mst()
        self.statusBar().showMessage(f"Выбран: {algorithm}")

    def add_vertex_at(self, pos: QPointF) -> None:
        if not self.graph_scene.can_place_vertex(pos):
            self.statusBar().showMessage("Слишком близко к другой вершине")
            return

        self.save_undo()
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

        self.save_undo()

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

        self.save_undo()

        self.graph = Graph()
        self.graph_scene.clear_graph()
        self.pending_vertex = None
        self.graphView.resetTransform()

        self.invalidate_mst()

        self.statusBar().showMessage("Полотно очищено")

    def build_mst(self) -> None:
        self.pause_playback()
        self.decision_timer.stop()
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
        self.step_index = None
        self.btnPreviousStep.setEnabled(False)
        self.btnNextStep.setEnabled(False)
        self.btnPlayPause.setEnabled(False)
        self.graph_scene.show_mst(result.edges)
        self.btnShowOriginalGraph.setEnabled(True)

        self.statusBar().showMessage(
            f"Остов построен. Рёбер: {len(result.edges)}, общий вес: {result.total_weight:g}"
        )

        self.progressSteps.setVisible(False)

    def show_original_graph(self) -> None:
        self.pause_playback()
        self.decision_timer.stop()
        self.graph_scene.show_original_graph()

        self.step_index = None
        self.btnPreviousStep.setEnabled(False)
        self.btnNextStep.setEnabled(False)
        self.btnPlayPause.setEnabled(False)
        self.btnShowOriginalGraph.setEnabled(False)

        self.statusBar().showMessage("Показан исходный граф")

        self.progressSteps.setVisible(False)

    def invalidate_mst(self) -> None:
        self.pause_playback()
        self.decision_timer.stop()
        self.last_result = None
        self.step_index = None

        self.graph_scene.show_original_graph()

        self.btnShowOriginalGraph.setEnabled(False)
        self.btnPreviousStep.setEnabled(False)
        self.btnNextStep.setEnabled(False)
        self.btnPlayPause.setEnabled(False)

        self.progressSteps.setVisible(False)

    def start_step_mode(self) -> None:
        self.pause_playback()
        self.decision_timer.stop()
        algorithm_index = self.comboAlgorithm.currentIndex()

        if algorithm_index not in (0, 1):
            QMessageBox.warning(self, "Алгоритм не выбран", "Сначала выберите алгоритм")
            return

        try:
            result = kruskal(self.graph) if algorithm_index == 0 else prim(self.graph)
        except GraphError as error:
            QMessageBox.warning(self, "Пошаговый режим", str(error))
            return

        self.pending_vertex = None
        self.graph_scene.select_vertex(None)

        self.last_result = result
        self.step_index = 0
        self.btnShowOriginalGraph.setEnabled(True)

        self.update_step_view()

    def update_step_view(self, preview: bool = False) -> None:
        if self.step_index is None or self.last_result is None:
            return

        steps = self.last_result.steps
        self.graph_scene.show_algorithm_step(steps, self.step_index, preview)
        self.progressSteps.setVisible(True)
        self.progressSteps.setRange(0, max(1, len(steps)))
        self.progressSteps.setValue(self.step_index)
        self.progressSteps.setFormat("Шаг %v из %m")

        self.btnPreviousStep.setEnabled(self.step_index > 0)
        self.btnNextStep.setEnabled(self.step_index < len(steps))

        self.btnPlayPause.setEnabled(bool(steps))

        if not steps:
            message = "Остов готов: одна вершина, общий вес 0"
        elif self.step_index == 0:
            message = f"Пошаговый режим: всего {len(steps)} шагов"
        else:
            step = steps[self.step_index - 1]
            decision = "рассматривается" if preview else ("принято" if step.accepted else "отклонено (цикл)")

            message = (
                f"Шаг {self.step_index}/{len(steps)}: "
                f"ребро {step.edge.start}–{step.edge.end}, "
                f"вес {step.edge.weight:g} — {decision}"
            )

            if self.step_index == len(steps):
                message += f". Остов построен, общий вес {self.last_result.total_weight:g}"

        self.statusBar().showMessage(message)

    def next_step(self) -> None:
        self.pause_playback()
        self.advance_playback()

    def previous_step(self) -> None:
        self.pause_playback()
        self.decision_timer.stop()

        if self.step_index is None:
            return

        if self.step_index > 0:
            self.step_index -= 1
            self.update_step_view()

    def toggle_playback(self) -> None:
        if self.step_index is None or self.last_result is None:
            return

        if not self.last_result.steps:
            return

        if self.playback_timer.isActive():
            self.pause_playback()
            return

        if self.step_index == len(self.last_result.steps):
            self.step_index = 0
            self.update_step_view()

        self.playback_timer.start()
        self.btnPlayPause.setText("⏸ Пауза")

    def pause_playback(self) -> None:
        self.playback_timer.stop()
        self.btnPlayPause.setText("▶ Воспроизвести")

    def advance_playback(self) -> None:
        if self.step_index is None or self.last_result is None:
            self.pause_playback()
            return

        if self.step_index >= len(self.last_result.steps):
            self.pause_playback()
            return

        self.decision_timer.stop()

        self.step_index += 1
        self.update_step_view(preview=True)

        duration = min(350, max(120, self.playback_timer.interval() // 3))
        self.decision_timer.start(duration)

        if self.step_index == len(self.last_result.steps):
            self.pause_playback()

    def change_playback_speed(self, index: int) -> None:
        intervals = (2000, 1000, 500)

        if 0 <= index < len(intervals):
            self.playback_timer.setInterval(intervals[index])

    def finish_step_preview(self) -> None:
        if self.step_index is not None and self.last_result is not None:
            self.update_step_view()

    def save_undo(self) -> None:
        positions = {}

        for vertex_id in self.graph.vertices:
            pos = self.graph_scene.vertex_position(vertex_id)
            positions[vertex_id] = (pos.x(), pos.y())

        state = (tuple(sorted(self.graph.vertices)), self.graph.edges, positions)
        self._undo_stack.append(state)

        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def undo(self) -> None:
        if not self._undo_stack:
            self.statusBar().showMessage("Нет действий для отмены")
            return

        vertices, edges, positions = self._undo_stack.pop()
        self.pending_vertex = None

        self.invalidate_mst()
        self.graph = Graph()

        for vertex_id in vertices:
            self.graph.add_vertex(vertex_id)

        for edge in edges:
            self.graph.add_edge(edge.start, edge.end, edge.weight)

        self.graph_scene.clear_graph()

        for vertex_id in vertices:
            self.graph_scene.add_vertex(vertex_id, QPointF(*positions[vertex_id]))

        for edge in edges:
            self.graph_scene.add_edge(edge.start, edge.end, edge.weight)

        self.statusBar().showMessage("Последнее действие отменено")

    def begin_vertex_move(self) -> None:
        self.save_undo()
        self.invalidate_mst()

    def rebuild_scene(self) -> None:
        positions = {
            vertex_id: self.graph_scene.vertex_position(vertex_id)
            for vertex_id in self.graph.vertices
        }

        self.graph_scene.clear_graph()

        for vertex_id in sorted(self.graph.vertices):
            self.graph_scene.add_vertex(vertex_id, positions[vertex_id])

        for edge in self.graph.edges:
            self.graph_scene.add_edge(edge.start, edge.end, edge.weight)

    def show_vertex_menu(self, vertex_id: int, pos: QPoint) -> None:
        menu = QMenu(self)
        delete_action = menu.addAction("Удалить вершину")

        if menu.exec(pos) != delete_action:
            return

        self.save_undo()
        self.graph.remove_vertex(vertex_id)
        self.invalidate_mst()
        self.rebuild_scene()

        self.pending_vertex = None
        self.graph_scene.select_vertex(None)

        self.statusBar().showMessage(f"Вершина {vertex_id} удалена")

    def show_edge_menu(self, start: int, end: int, pos: QPoint) -> None:
        menu = QMenu(self)
        edit_action = menu.addAction("Изменить вес")
        delete_action = menu.addAction("Удалить ребро")

        action = menu.exec(pos)

        if action == delete_action:
            self.save_undo()
            self.graph.remove_edge(start, end)
            self.invalidate_mst()
            self.rebuild_scene()
            self.pending_vertex = None
            self.graph_scene.select_vertex(None)
            self.statusBar().showMessage(f"Ребро {start}–{end} удалено")

        elif action == edit_action:
            edge = next(e for e in self.graph.edges if e.start == start and e.end == end)

            weight, ok = QInputDialog.getDouble(
                self, "Изменение веса", f"Новый вес ребра {start}–{end}:",
                edge.weight, -1000000.0, 1000000.0, 2
            )

            if not ok or weight == edge.weight:
                return

            self.save_undo()
            self.graph.set_edge_weight(start, end, weight)
            self.invalidate_mst()
            self.rebuild_scene()
            self.pending_vertex = None
            self.graph_scene.select_vertex(None)

            self.statusBar().showMessage(f"Вес ребра {start}–{end} изменён на {weight:g}")

