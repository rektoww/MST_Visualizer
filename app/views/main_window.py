from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QInputDialog, QMessageBox, QGraphicsView, QMenu, QTableWidgetItem, QDialog, QFileDialog, QApplication
from PyQt6.QtCore import Qt, QPointF, QEvent, QTimer, QPoint, QSettings
from PyQt6.QtGui import QShortcut, QKeySequence

from app.core.graph import Graph
from app.views.graph_scene import GraphScene
from app.core.exceptions import GraphError
from app.views.generate_graph_dialog import GenerateGraphDialog
from app.core.graph_generator import generate_random_graph
from app.core.graph_storage import save_graph, load_graph, graph_to_dict, edge_to_dict
from app.views.settings_dialog import SettingsDialog
from app.views.calculations_loader import CalculationsLoader
from app.i18n import translate
from app.core.algorithms.result import MSTResult
from app.event_logger import queue_calculation

from app.core.algorithms.kruskal import kruskal
from app.core.algorithms.prim import prim

from math import isfinite, cos, sin, pi, hypot
from time import perf_counter


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        # Загрузка интерфейса
        project_dir = Path(__file__).resolve().parents[2]
        uic.loadUi(str(project_dir / "ui" / "main_window.ui"), self)

        # Настройки приложения
        self.settings = QSettings("MSTVisualizer", "MSTVisualizer")

        self.theme = self.settings.value("theme", "light")
        if self.theme not in ("light", "dark"):
            self.theme = "light"

        self.language = self.settings.value("language", "ru")
        if self.language not in ("ru", "en"):
            self.language = "ru"

        self.apply_theme(self.theme)

        # Пути и состояние приложения
        self.graphs_dir = project_dir / "data" / "graphs"
        self.current_file_path: Path | None = None
        self.history_loader: CalculationsLoader | None = None

        self.pending_vertex: int | None = None
        self.last_result = None
        self.execution_time_ms: float | None = None
        self.step_index: int | None = None
        self._undo_stack = []

        # Граф и графическая сцена
        self.graph = Graph()
        self.graph_scene = GraphScene(self)
        self.graph_scene.setSceneRect(0, 0, 1200, 900)

        self.graphView.setScene(self.graph_scene)
        self.graphView.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.graphView.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.graphView.viewport().installEventFilter(self)

        # Начальное состояние элементов интерфейса
        self.btnBuildMst.setEnabled(True)
        self.btnStepMode.setEnabled(True)
        self.btnGenerateGraph.setEnabled(True)
        self.btnShowOriginalGraph.setEnabled(False)

        self.btnPreviousStep.setEnabled(False)
        self.btnNextStep.setEnabled(False)
        self.btnPlayPause.setEnabled(False)

        self.progressSteps.setVisible(False)
        self.comboPlaybackSpeed.setCurrentIndex(1)

        # Таймеры пошагового воспроизведения
        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(1000)

        self.decision_timer = QTimer(self)
        self.decision_timer.setSingleShot(True)

        # Сигналы графической сцены
        self.graph_scene.vertex_move_started.connect(self.begin_vertex_move)
        self.graph_scene.vertex_moved.connect(
            lambda vertex_id: self.statusBar().showMessage(self.localized_text("vertex_moved", vertex_id=vertex_id))
        )
        self.graph_scene.vertex_moved.connect(lambda vertex_id: self.refresh_tables())
        self.graph_scene.vertex_clicked.connect(self.on_vertex_clicked)
        self.graph_scene.empty_space_clicked.connect(self.add_vertex_at)
        self.graph_scene.vertex_context_requested.connect(self.show_vertex_menu)
        self.graph_scene.edge_context_requested.connect(self.show_edge_menu)

        # Кнопки управления графом
        self.btnGenerateGraph.clicked.connect(self.open_generate_graph_dialog)
        self.btnClearCanvas.clicked.connect(self.clear_canvas)
        self.btnBuildMst.clicked.connect(self.build_mst)
        self.btnShowOriginalGraph.clicked.connect(self.show_original_graph)
        self.comboAlgorithm.currentTextChanged.connect(self.on_algorithm_changed)

        # Управление пошаговым воспроизведением
        self.btnStepMode.clicked.connect(self.start_step_mode)
        self.btnPreviousStep.clicked.connect(self.previous_step)
        self.btnNextStep.clicked.connect(self.next_step)
        self.btnPlayPause.clicked.connect(self.toggle_playback)
        self.comboPlaybackSpeed.currentIndexChanged.connect(self.change_playback_speed)

        self.playback_timer.timeout.connect(self.advance_playback)
        self.decision_timer.timeout.connect(self.finish_step_preview)

        # Редактирование графа через таблицы
        self.btnAddVertexTable.clicked.connect(self.add_vertex_from_table)
        self.btnDeleteVertexTable.clicked.connect(self.delete_vertex_from_table)
        self.btnAddEdgeTable.clicked.connect(self.add_edge_from_table)
        self.btnDeleteEdgeTable.clicked.connect(self.delete_edge_from_table)

        self.tableVertices.itemChanged.connect(self.on_vertex_table_changed)
        self.tableEdges.itemChanged.connect(self.on_edge_table_changed)

        # История расчётов
        self.btnRefreshHistory.clicked.connect(self.load_history)

        # Главное меню
        self.actionSave.triggered.connect(self.save_current_graph)
        self.actionSaveAs.triggered.connect(self.save_current_graph_as)
        self.actionLoad.triggered.connect(self.load_graph_from_file)
        self.actionSettings.triggered.connect(self.show_settings)
        self.actionExit.triggered.connect(self.close)

        # Отмена последнего действия
        self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.undo_shortcut.activated.connect(self.undo)

        # Применение локализации
        self.update_language()
        self.statusBar().showMessage(translate("ready", self.language))

    def localized_text(self, key: str, **values) -> str:
        return translate(key, self.language).format(**values)

    def localized_error(self, error: GraphError) -> str:
        if error.code is None:
            return str(error)

        return self.localized_text(
            error.code,
            **error.params
        )

    def confirm_action(self, title_key: str, message_key: str) -> bool:
        dialog = QMessageBox(self)

        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(self.localized_text(title_key))
        dialog.setText(self.localized_text(message_key))

        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        dialog.setDefaultButton(QMessageBox.StandardButton.No)

        dialog.button(QMessageBox.StandardButton.Yes).setText(self.localized_text("yes"))

        dialog.button(QMessageBox.StandardButton.No).setText(self.localized_text("no"))

        return dialog.exec() == QMessageBox.StandardButton.Yes

    def on_algorithm_changed(self, algorithm: str) -> None:
        self.invalidate_mst()
        self.statusBar().showMessage(self.localized_text("algorithm_selected", algorithm=algorithm))

    def add_vertex_at(self, pos: QPointF) -> None:
        if not self.graph_scene.can_place_vertex(pos):
            self.statusBar().showMessage(self.localized_text("vertex_too_close"))
            return

        self.save_undo()
        self.invalidate_mst()

        vertex_id = max(self.graph.vertices, default=0) + 1

        self.graph.add_vertex(vertex_id)
        self.graph_scene.add_vertex(vertex_id, pos)
        self.refresh_tables()
        self.statusBar().showMessage(self.localized_text("vertex_added", vertex_id=vertex_id))

    def on_vertex_clicked(self, vertex_id: int) -> None:
        if self.pending_vertex is None:
            self.pending_vertex = vertex_id
            self.graph_scene.select_vertex(vertex_id)
            self.statusBar().showMessage(self.localized_text("first_vertex_selected", vertex_id=vertex_id))
            return

        first = self.pending_vertex
        self.pending_vertex = None
        self.graph_scene.select_vertex(None)

        if first == vertex_id:
            self.statusBar().showMessage(self.localized_text("vertex_selection_cancelled"))
            return

        if self.graph.has_edge(first, vertex_id):
            QMessageBox.warning(
                self, self.localized_text("edge_exists_title"),
                self.localized_text("vertices_already_connected", first=first, second=vertex_id)
            )
            return

        weight, ok = QInputDialog.getDouble(
            self, self.localized_text("edge_weight_title"), self.localized_text("edge_weight_between", first=first, second=vertex_id),
            1.0, -1000000.0, 1000000.0, 2
        )

        if not ok:
            self.statusBar().showMessage(self.localized_text("edge_add_cancelled"))
            return

        self.save_undo()

        try:
            self.graph.add_edge(first, vertex_id, weight)
        except GraphError as error:
            QMessageBox.warning(self, self.localized_text("edge_add_error_title"), self.localized_error(error))
            return

        self.invalidate_mst()
        self.graph_scene.add_edge(first, vertex_id, weight)
        self.refresh_tables()
        self.statusBar().showMessage(self.localized_text("edge_added", start=first, end=vertex_id, weight=f"{weight:g}"))

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
            self.statusBar().showMessage(self.localized_text("canvas_already_empty"))
            return

        if not self.confirm_action("clear_canvas_title", "clear_canvas_question"):
            return

        self.save_undo(restore_file_path=True)

        self.current_file_path = None
        self.graph = Graph()
        self.graph_scene.clear_graph()
        self.pending_vertex = None
        self.graphView.resetTransform()

        self.invalidate_mst()

        self.refresh_tables()
        self.statusBar().showMessage(self.localized_text("canvas_cleared"))

    def build_mst(self) -> None:
        self.pause_playback()
        self.decision_timer.stop()
        algorithm_index = self.comboAlgorithm.currentIndex()

        if algorithm_index not in (0, 1):
            QMessageBox.warning(self, self.localized_text("algorithm_not_selected_title"), self.localized_text("select_algorithm_first"))
            return

        try:
            started = perf_counter()

            result = kruskal(self.graph) if algorithm_index == 0 else prim(self.graph)

            self.execution_time_ms = (perf_counter() - started) * 1000

        except GraphError as error:
            QMessageBox.warning(self, self.localized_text("build_error_title"), self.localized_error(error))
            return

        self.last_result = result
        self.step_index = None
        self.update_result_labels()
        self.btnPreviousStep.setEnabled(False)
        self.btnNextStep.setEnabled(False)
        self.btnPlayPause.setEnabled(False)
        self.graph_scene.show_mst(result.edges)
        self.btnShowOriginalGraph.setEnabled(True)
        self.queue_current_calculation(result, algorithm_index, "build")

        self.statusBar().showMessage(
            self.localized_text("mst_built", count=len(result.edges), weight=f"{result.total_weight:g}")
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
        self.last_result = None
        self.execution_time_ms = None
        self.update_result_labels()

        self.statusBar().showMessage(self.localized_text("original_graph_shown"))

        self.progressSteps.setVisible(False)

    def invalidate_mst(self) -> None:
        self.pause_playback()
        self.decision_timer.stop()
        self.last_result = None
        self.step_index = None
        self.execution_time_ms = None

        self.update_result_labels()

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
            QMessageBox.warning(self, self.localized_text("algorithm_not_selected_title"), self.localized_text("select_algorithm_first"))
            return

        try:
            started = perf_counter()
            result = kruskal(self.graph) if algorithm_index == 0 else prim(self.graph)
            self.execution_time_ms = (perf_counter() - started) * 1000
        except GraphError as error:
            QMessageBox.warning(self, self.localized_text("step_mode"), self.localized_error(error))
            return

        self.pending_vertex = None
        self.graph_scene.select_vertex(None)

        self.last_result = result
        self.step_index = 0
        self.btnShowOriginalGraph.setEnabled(True)
        self.queue_current_calculation(result, algorithm_index, "step")

        self.update_step_view()

    def update_step_view(self, preview: bool = False) -> None:
        if self.step_index is None or self.last_result is None:
            return

        steps = self.last_result.steps
        self.graph_scene.show_algorithm_step(steps, self.step_index, preview)
        self.progressSteps.setVisible(True)
        self.progressSteps.setRange(0, max(1, len(steps)))
        self.progressSteps.setValue(self.step_index)
        self.update_result_labels(preview)
        self.progressSteps.setFormat(translate("step_progress", self.language))

        self.btnPreviousStep.setEnabled(self.step_index > 0)
        self.btnNextStep.setEnabled(self.step_index < len(steps))

        self.btnPlayPause.setEnabled(bool(steps))

        if not steps:
            message = self.localized_text("single_vertex_mst")
        elif self.step_index == 0:
            message = self.localized_text("step_mode_started", count=len(steps))
        else:
            step = steps[self.step_index - 1]
            decision_key = (
                "step_preview" if preview
                else "step_accepted" if step.accepted
                else "step_rejected"
            )
            decision = self.localized_text(decision_key)

            message = self.localized_text(
                "step_status",
                current=self.step_index,
                total=len(steps),
                start=step.edge.start,
                end=step.edge.end,
                weight=f"{step.edge.weight:g}",
                decision=decision
            )

            if self.step_index == len(steps) and not preview:
                message += self.localized_text(
                    "step_mst_finished",
                    weight=f"{self.last_result.total_weight:g}"
                )

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
        self.btnPlayPause.setText(translate("pause", self.language))

    def pause_playback(self) -> None:
        self.playback_timer.stop()
        self.btnPlayPause.setText(translate("play", self.language))

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

    def save_undo(self, restore_file_path: bool = False) -> None:
        positions = {}

        for vertex_id in self.graph.vertices:
            pos = self.graph_scene.vertex_position(vertex_id)
            positions[vertex_id] = (pos.x(), pos.y())

        state = (tuple(sorted(self.graph.vertices)), self.graph.edges, positions, self.current_file_path, restore_file_path)
        self._undo_stack.append(state)

        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def undo(self) -> None:
        if not self._undo_stack:
            self.statusBar().showMessage(self.localized_text("nothing_to_undo"))
            return

        vertices, edges, positions, file_path, restore_file_path = self._undo_stack.pop()
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

        if restore_file_path:
            self.current_file_path = file_path

        self.refresh_tables()
        self.statusBar().showMessage(self.localized_text("last_action_undone"))

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

        self.refresh_tables()

    def show_vertex_menu(self, vertex_id: int, pos: QPoint) -> None:
        menu = QMenu(self)
        delete_action = menu.addAction(self.localized_text("vertex_delete_action"))

        if menu.exec(pos) != delete_action:
            return

        self.save_undo()
        self.graph.remove_vertex(vertex_id)
        self.invalidate_mst()
        self.rebuild_scene()

        self.pending_vertex = None
        self.graph_scene.select_vertex(None)

        self.statusBar().showMessage(self.localized_text("vertex_removed", vertex_id=vertex_id))

    def show_edge_menu(self, start: int, end: int, pos: QPoint) -> None:
        menu = QMenu(self)
        edit_action = menu.addAction(self.localized_text("edit_weight_action"))
        delete_action = menu.addAction(self.localized_text("edge_delete_action"))

        action = menu.exec(pos)

        if action == delete_action:
            self.save_undo()
            self.graph.remove_edge(start, end)
            self.invalidate_mst()
            self.rebuild_scene()
            self.pending_vertex = None
            self.graph_scene.select_vertex(None)
            self.statusBar().showMessage(self.localized_text("edge_removed", start=start, end=end))

        elif action == edit_action:
            edge = next(e for e in self.graph.edges if e.start == start and e.end == end)

            weight, ok = QInputDialog.getDouble(
                self, self.localized_text("change_weight_title"), self.localized_text("change_weight_prompt", start=start, end=end),
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

            self.statusBar().showMessage(self.localized_text("edge_weight_changed", start=start, end=end, weight=f"{weight:g}"))

    def refresh_tables(self) -> None:
        self.tableVertices.blockSignals(True)
        vertices = sorted(self.graph.vertices)
        self.tableVertices.setRowCount(len(vertices))

        for row, vertex_id in enumerate(vertices):
            pos = self.graph_scene.vertex_position(vertex_id)
            values = (str(vertex_id), f"{pos.x():.1f}", f"{pos.y():.1f}")

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)

                if column == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                self.tableVertices.setItem(row, column, item)

        self.tableVertices.blockSignals(False)

        self.tableEdges.blockSignals(True)
        edges = self.graph.edges
        self.tableEdges.setRowCount(len(edges))

        for row, edge in enumerate(edges):
            values = (str(edge.start), str(edge.end), f"{edge.weight:g}")

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)

                if column != 2:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                self.tableEdges.setItem(row, column, item)


        self.tableEdges.blockSignals(False)

    def on_edge_table_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 2:
            return

        row = item.row()
        start = int(self.tableEdges.item(row, 0).text())
        end = int(self.tableEdges.item(row, 1).text())

        edge = next(e for e in self.graph.edges if e.start == start and e.end == end)

        try:
            weight = float(item.text())
            if not -1000000 <= weight <= 1000000:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, self.localized_text("error_title"), self.localized_text("invalid_weight"))
            self.refresh_tables()
            return

        if weight == edge.weight:
            return

        self.save_undo()
        self.graph.set_edge_weight(start, end, weight)
        self.invalidate_mst()
        self.rebuild_scene()

        self.statusBar().showMessage(self.localized_text("edge_weight_changed", start=start, end=end, weight=f"{weight:g}"))

    def add_vertex_from_table(self) -> None:
        rect = self.graph_scene.sceneRect()

        for y in range(70, int(rect.bottom()) - 50, 90):
            for x in range(70, int(rect.right()) - 50, 90):
                pos = QPointF(x, y)

                if self.graph_scene.can_place_vertex(pos):
                    self.add_vertex_at(pos)
                    return

        QMessageBox.warning(self, self.localized_text("add_vertex_title"), self.localized_text("no_space_for_vertex"))

    def add_edge_from_table(self) -> None:
        vertices = [str(vertex_id) for vertex_id in sorted(self.graph.vertices)]

        if len(vertices) < 2:
            QMessageBox.warning(self, self.localized_text("add_edge_title"), self.localized_text("requires_two_vertices"))
            return

        first, ok = QInputDialog.getItem(
            self, self.localized_text("add_edge_title"), self.localized_text("start_vertex_prompt"),
            vertices, 0, False
        )

        if not ok:
            return

        remaining = [vertex_id for vertex_id in vertices if vertex_id != first]

        second, ok = QInputDialog.getItem(
            self, self.localized_text("add_edge_title"), self.localized_text("end_vertex_prompt"),
            remaining, 0, False
        )

        if not ok:
            return

        start, end = int(first), int(second)

        if self.graph.has_edge(start, end):
            QMessageBox.warning(self, self.localized_text("add_edge_title"), self.localized_text("edge_already_exists"))
            return

        weight, ok = QInputDialog.getDouble(
            self, self.localized_text("add_edge_title"), self.localized_text("edge_weight_prompt"),
            1.0, -1000000.0, 1000000.0, 2
        )

        if not ok:
            return

        self.save_undo()
        self.graph.add_edge(start, end, weight)
        self.invalidate_mst()
        self.graph_scene.add_edge(start, end, weight)
        self.refresh_tables()

        self.statusBar().showMessage(self.localized_text("edge_added", start=start, end=end, weight=f"{weight:g}"))

    def delete_vertex_from_table(self) -> None:
        row = self.tableVertices.currentRow()

        if row < 0:
            QMessageBox.warning(self, self.localized_text("delete_vertex_title"), self.localized_text("select_row_first"))
            return

        vertex_id = int(self.tableVertices.item(row, 0).text())

        self.save_undo()
        self.graph.remove_vertex(vertex_id)
        self.invalidate_mst()
        self.rebuild_scene()

        self.pending_vertex = None
        self.graph_scene.select_vertex(None)

        self.statusBar().showMessage(self.localized_text("vertex_removed", vertex_id=vertex_id))

    def delete_edge_from_table(self) -> None:
        row = self.tableEdges.currentRow()

        if row < 0:
            QMessageBox.warning(self, self.localized_text("delete_edge_title"), self.localized_text("select_row_first"))
            return

        start = int(self.tableEdges.item(row, 0).text())
        end = int(self.tableEdges.item(row, 1).text())

        self.save_undo()
        self.graph.remove_edge(start, end)
        self.invalidate_mst()
        self.rebuild_scene()

        self.pending_vertex = None
        self.graph_scene.select_vertex(None)

        self.statusBar().showMessage(self.localized_text("edge_removed", start=start, end=end))

    def on_vertex_table_changed(self, item: QTableWidgetItem) -> None:
        if item.column() not in (1, 2):
            return

        row = item.row()
        vertex_id = int(self.tableVertices.item(row, 0).text())

        try:
            x = float(self.tableVertices.item(row, 1).text())
            y = float(self.tableVertices.item(row, 2).text())

            if not isfinite(x) or not isfinite(y):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, self.localized_text("invalid_coord_title"), self.localized_text("invalid_coords"))
            self.refresh_tables()
            return

        new_pos = QPointF(x, y)
        old_pos = self.graph_scene.vertex_position(vertex_id)

        if new_pos == old_pos:
            self.refresh_tables()
            return

        bounds = self.graph_scene.sceneRect().adjusted(18, 18, -18, -18)

        if not bounds.contains(new_pos):
            QMessageBox.warning(self, self.localized_text("invalid_coord_title"), self.localized_text("vertex_out_of_bounds"))
            self.refresh_tables()
            return

        if not self.graph_scene.can_place_vertex(new_pos, vertex_id):
            QMessageBox.warning(self, self.localized_text("invalid_coord_title"), self.localized_text("vertex_too_close"))
            self.refresh_tables()
            return

        self.save_undo()
        self.invalidate_mst()
        self.graph_scene.move_vertex(vertex_id, new_pos)
        self.refresh_tables()

        self.statusBar().showMessage(self.localized_text("vertex_coords_changed", vertex_id=vertex_id))

    def show_settings(self) -> None:
        dialog = SettingsDialog(self.theme, self.language, self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_theme = dialog.selected_theme()
        new_language = dialog.selected_language()

        if new_theme != self.theme:
            self.apply_theme(new_theme)
            self.theme = new_theme
            self.settings.setValue("theme", new_theme)

        if new_language != self.language:
            self.language = new_language
            self.settings.setValue("language", new_language)
            self.update_language()

        self.statusBar().showMessage(translate("settings_saved", self.language))

    def open_generate_graph_dialog(self) -> None:
        dialog = GenerateGraphDialog(self, self.language)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        vertex_count = dialog.spinVertexCount.value()
        edge_count = dialog.spinEdgeCount.value()
        min_weight = dialog.spinMinWeight.value()
        max_weight = dialog.spinMaxWeight.value()

        if self.graph.vertices:
            if not self.confirm_action("generate_graph_title", "replace_graph_prompt"):
                return

        try:
            new_graph = generate_random_graph(vertex_count, edge_count, min_weight, max_weight)
        except GraphError as error:
            QMessageBox.warning(self, self.localized_text("generation_error_title"), self.localized_error(error))
            return

        self.save_undo(restore_file_path=True)
        self.invalidate_mst()
        self.pending_vertex = None
        self.current_file_path = None

        self.graph = new_graph
        self.graph_scene.clear_graph()
        self.graphView.resetTransform()

        rect = self.graph_scene.sceneRect()
        center = rect.center()
        radius = min(rect.width(), rect.height()) * 0.33

        for index, vertex_id in enumerate(sorted(self.graph.vertices)):
            angle = 2 * pi * index / vertex_count - pi / 2

            x = center.x() + radius * cos(angle)
            y = center.y() + radius * sin(angle)

            self.graph_scene.add_vertex(vertex_id, QPointF(x, y))

        for edge in self.graph.edges:
            self.graph_scene.add_edge(edge.start, edge.end, edge.weight)

        self.refresh_tables()
        self.tabGraphEditor.setCurrentWidget(self.tabCanvas)

        self.statusBar().showMessage(
            self.localized_text("generated_graph", vertices=vertex_count, edges=edge_count)
        )

    def write_graph_to_file(self, path: Path) -> None:
        positions = {}

        for vertex_id in self.graph.vertices:
            pos = self.graph_scene.vertex_position(vertex_id)
            positions[vertex_id] = (pos.x(), pos.y())

        try:
            save_graph(self.graph, positions, path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(
                self, self.localized_text("save_error_title"), str(error)
            )
            return

        self.current_file_path = path
        self.statusBar().showMessage(self.localized_text("graph_saved", filename=path.name))

    def save_current_graph(self) -> None:
        if self.current_file_path is not None:
            self.write_graph_to_file(self.current_file_path)
            return

        index = 1

        while True:
            path = self.graphs_dir / f"graph_{index:03d}.json"

            if not path.exists():
                break

            index += 1

        self.write_graph_to_file(path)

    def save_current_graph_as(self) -> None:
        suggested_path = (
                self.current_file_path
                or self.graphs_dir / "graph.json"
        )

        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            self.localized_text("save_graph_as_title"),
            str(suggested_path),
            self.localized_text("graph_files_filter")
        )

        if not filename:
            return

        path = Path(filename)

        if path.suffix.lower() != ".json":
            path = Path(str(path) + ".json")

        self.write_graph_to_file(path)

    def load_graph_from_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, self.localized_text("load_graph_title"),
            str(self.graphs_dir), self.localized_text("graph_files_filter")
        )

        if not filename:
            return

        path = Path(filename)

        try:
            new_graph, positions = load_graph(path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, self.localized_text("load_error_title"), str(error))
            return

        bounds = self.graph_scene.sceneRect().adjusted(18, 18, -18, -18)

        for vertex_id, (x, y) in positions.items():
            if not bounds.contains(QPointF(x, y)):
                QMessageBox.warning(
                    self, self.localized_text("load_error_title"),
                    self.localized_text("loaded_vertex_out_of_bounds", vertex_id=vertex_id)
                )
                return

        vertices = list(positions.items())

        for index, (first_id, (x1, y1)) in enumerate(vertices):
            for second_id, (x2, y2) in vertices[index + 1:]:
                if hypot(x1 - x2, y1 - y2) < 50:
                    QMessageBox.warning(
                        self, self.localized_text("load_error_title"),
                        self.localized_text("loaded_vertices_too_close", first=first_id, second=second_id)
                    )
                    return

        if self.graph.vertices:
            if not self.confirm_action("load_graph_title", "replace_graph_prompt"):
                return

        self.save_undo(restore_file_path=True)
        self.invalidate_mst()
        self.pending_vertex = None

        self.graph = new_graph
        self.graph_scene.clear_graph()
        self.graphView.resetTransform()

        for vertex_id, (x, y) in sorted(positions.items()):
            self.graph_scene.add_vertex(vertex_id, QPointF(x, y))

        for edge in self.graph.edges:
            self.graph_scene.add_edge(
                edge.start, edge.end, edge.weight
            )

        self.current_file_path = path

        self.refresh_tables()
        self.tabGraphEditor.setCurrentWidget(self.tabCanvas)

        self.statusBar().showMessage(self.localized_text("graph_loaded", filename=path.name))

    def apply_theme(self, theme: str) -> None:
        theme_path = (
                Path(__file__).resolve().parents[2]
                / "styles"
                / f"{theme}.qss"
        )

        stylesheet = theme_path.read_text(encoding="utf-8")

        QApplication.instance().setStyleSheet(stylesheet)

    def update_language(self) -> None:
        lang = self.language

        self.menuFile.setTitle(translate("file", lang))
        self.controlPanel.setTitle(translate("controls", lang))

        actions = [
            (self.actionSave, "save"),
            (self.actionSaveAs, "save_as"),
            (self.actionLoad, "load"),
            (self.actionSettings, "settings"),
            (self.actionExit, "exit")
        ]

        for action, key in actions:
            action.setText(translate(key, lang))

        widgets = [
            (self.labelVerticesTable, "vertices"),
            (self.labelEdgesTable, "edges"),
            (self.btnAddVertexTable, "add_vertex"),
            (self.btnDeleteVertexTable, "delete_vertex"),
            (self.btnAddEdgeTable, "add_edge"),
            (self.btnDeleteEdgeTable, "delete_edge"),
            (self.labelAlgorithm, "algorithm"),
            (self.btnBuildMst, "build_mst"),
            (self.btnShowOriginalGraph, "original_graph"),
            (self.btnGenerateGraph, "generate_graph"),
            (self.btnClearCanvas, "clear_canvas"),
            (self.btnStepMode, "step_mode"),
            (self.btnPreviousStep, "previous_step"),
            (self.btnNextStep, "next_step"),
            (self.label, "speed"),
        ]

        for widget, key in widgets:
            widget.setText(translate(key, lang))

        self.tabGraphEditor.setTabText(
            self.tabGraphEditor.indexOf(self.tabCanvas),
            translate("canvas", lang)
        )

        self.tabGraphEditor.setTabText(
            self.tabGraphEditor.indexOf(self.tabTables),
            translate("tables", lang)
        )

        self.tableEdges.setHorizontalHeaderLabels([
            translate("start", lang),
            translate("end", lang),
            translate("weight", lang)
        ])

        self.comboAlgorithm.blockSignals(True)

        self.comboAlgorithm.setItemText(0, translate("kruskal", lang))
        self.comboAlgorithm.setItemText(1, translate("prim", lang))

        self.comboAlgorithm.blockSignals(False)

        playback_key = "pause" if self.playback_timer.isActive() else "play"
        self.btnPlayPause.setText(translate(playback_key, lang))

        self.progressSteps.setFormat(translate("step_progress", lang))

        self.update_result_labels(preview=self.decision_timer.isActive())

    def update_result_labels(self, preview: bool = False) -> None:
        if self.last_result is None:
            weight_text = "—"
            edge_count = 0

        elif self.step_index is None:
            weight_text = f"{self.last_result.total_weight:g}"
            edge_count = len(self.last_result.edges)

        else:
            steps = self.last_result.steps[:self.step_index]

            if preview:
                steps = steps[:-1]

            selected_edges = [
                step.edge for step in steps if step.accepted
            ]

            edge_count = len(selected_edges)
            weight = sum(edge.weight for edge in selected_edges)
            weight_text = f"{weight:g}"

        self.labelTotalWeight.setText(
            translate("total_weight", self.language).format(
                value=weight_text
            )
        )

        self.labelSelectedEdges.setText(
            translate("selected_edges", self.language).format(
                count=edge_count
            )
        )

        time_value = "—"

        if self.execution_time_ms is not None:
            unit = "мс" if self.language == "ru" else "ms"
            time_value = f"{self.execution_time_ms:.3f} {unit}"

        self.labelExecutionTime.setText(self.localized_text("execution_time", value=time_value))

    def queue_current_calculation(self, result: MSTResult, algorithm_index: int, run_mode: str) -> None:
        positions = {}

        for vertex_id in self.graph.vertices:
            pos = self.graph_scene.vertex_position(vertex_id)
            positions[vertex_id] = (pos.x(), pos.y())

        data = {
            "algorithm": "kruskal" if algorithm_index == 0 else "prim",
            "run_mode": run_mode,
            "vertex_count": len(self.graph.vertices),
            "edge_count": len(self.graph.edges),
            "graph_data": graph_to_dict(self.graph, positions),
            "result_edges": [edge_to_dict(edge) for edge in result.edges],
            "steps": [{"edge": edge_to_dict(step.edge), "accepted": step.accepted} for step in result.steps],
            "total_weight": result.total_weight,
            "duration_ms": self.execution_time_ms
        }

        queue_calculation(data)

    def load_history(self) -> None:
        if self.history_loader is not None:
            return

        self.btnRefreshHistory.setEnabled(False)

        self.history_loader = CalculationsLoader(self)
        self.history_loader.loaded.connect(self.show_history)
        self.history_loader.failed.connect(self.history_load_failed)
        self.history_loader.finished.connect(self.history_load_finished)
        self.history_loader.start()

    def show_history(self, calculations: list[dict]) -> None:
        self.tableHistory.setSortingEnabled(False)
        self.tableHistory.setRowCount(len(calculations))

        for row, calculation in enumerate(calculations):
            algorithm = self.localized_text(calculation["algorithm"])
            mode = "Обычный" if calculation["run_mode"] == "build" else "Пошаговый"

            values = [
                calculation["id"],
                calculation["created_at"].strftime("%d.%m.%Y %H:%M:%S"),
                algorithm,
                mode,
                calculation["vertex_count"],
                calculation["edge_count"],
                f'{calculation["total_weight"]:.2f}',
                f'{calculation["duration_ms"]:.4f}'
            ]

            for column, value in enumerate(values):
                self.tableHistory.setItem(row, column, QTableWidgetItem(str(value)))

        self.tableHistory.setSortingEnabled(True)
        self.statusBar().showMessage(f"Загружено расчётов: {len(calculations)}")

    def history_load_failed(self) -> None:
        self.statusBar().showMessage("Не удалось загрузить историю расчётов")

    def history_load_finished(self) -> None:
        self.btnRefreshHistory.setEnabled(True)
        self.history_loader.deleteLater()
        self.history_loader = None


