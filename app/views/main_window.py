import logging
import os
from pathlib import Path

import json
from PyQt6 import uic
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QGraphicsView, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QStyledItemDelegate, QTableWidgetItem,
)
from PyQt6.QtCore import Qt, QPointF, QEvent, QTimer, QPoint, QSettings
from PyQt6.QtGui import QShortcut, QKeySequence

from app.core.graph import Graph
from app.views.graph_scene import GraphScene
from app.core.exceptions import GraphError
from app.views.generate_graph_dialog import GenerateGraphDialog
from app.core.graph_generator import generate_random_graph
from app.core.graph_storage import save_graph, load_graph, graph_to_dict, edge_to_dict
from app.database.calculations import decode_calculation
from app.views.settings_dialog import SettingsDialog
from app.views.calculations_loader import CalculationsLoader, CalculationDetailsLoader
from app.i18n import translate
from app.core.algorithms.result import MSTResult
from app.event_logger import queue_calculation, record_event
from app.views.event_logs_loader import EventLogsLoader

from app.core.algorithms.kruskal import kruskal
from app.core.algorithms.prim import prim
from math import isfinite, cos, sin, pi
from sys import float_info
from time import monotonic, perf_counter


logger = logging.getLogger(__name__)
SHUTDOWN_TIMEOUT_SECONDS = 8


class ExactNumberDelegate(QStyledItemDelegate):
    def setEditorData(self, editor, index) -> None:
        super().setEditorData(editor, index)
        value = index.data(Qt.ItemDataRole.UserRole)
        if value is not None and isinstance(editor, QLineEdit):
            editor.setText(str(value))
            editor.selectAll()


class SortableTableItem(QTableWidgetItem):
    def __lt__(self, other: QTableWidgetItem) -> bool:
        value = self.data(Qt.ItemDataRole.UserRole)
        other_value = other.data(Qt.ItemDataRole.UserRole)
        if value is not None and other_value is not None:
            return value < other_value
        return super().__lt__(other)


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

        self.comboEventLevel.addItem("", None)

        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            self.comboEventLevel.addItem(level, level)

        # Пути и состояние приложения
        container_graphs_dir = os.getenv("MST_GRAPH_DIR")
        self.graphs_dir = Path(container_graphs_dir) if container_graphs_dir else project_dir / "data" / "graphs"
        self.current_file_path: Path | None = None
        self.history_loader: CalculationsLoader | None = None
        self.calculation_loader: CalculationDetailsLoader | None = None
        self.history_records: list[dict] = []
        self.events_loader: EventLogsLoader | None = None
        self.events_records: list[dict] = []

        self.pending_vertex: int | None = None
        self.last_result = None
        self.execution_time_ms: float | None = None
        self.step_index: int | None = None
        self._undo_stack = []
        self._clean_state = (frozenset(), frozenset(), {})
        self._close_prompt_active = False
        self._external_shutdown = False
        self._shutdown_deadline = None
        self._shutdown_ready = False
        self._deferred_calculation = None
        self._calculation_saves = []
        self._history_saved = False
        self._history_save_failures = 0
        self._history_save_unknown = 0
        self._failures_at_shutdown = 0
        self.history_save_status = QLabel(self)
        self.statusBar().addPermanentWidget(self.history_save_status)
        self.background_timer = QTimer(self, interval=100)
        self.background_timer.timeout.connect(self.poll_background_work)

        # Граф и графическая сцена
        self.graph = Graph()
        self.graph_scene = GraphScene(self)
        self.graph_scene.setSceneRect(0, 0, 1200, 900)
        self.tableVertices.setItemDelegate(ExactNumberDelegate(self.tableVertices))
        self.tableEdges.setItemDelegate(ExactNumberDelegate(self.tableEdges))
        for table in (self.tableHistory, self.tableEvents):
            table.horizontalHeader().setSortIndicator(1, Qt.SortOrder.DescendingOrder)

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
        self.tableHistory.cellDoubleClicked.connect(self.open_history_calculation)

        # Журнал
        self.btnRefreshEvents.clicked.connect(self.load_event_logs)
        self.comboEventLevel.currentIndexChanged.connect(self.render_event_logs)

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

        try:
            return dialog.exec() == QMessageBox.StandardButton.Yes
        finally:
            dialog.deleteLater()

    def graph_positions(self) -> dict[int, tuple[float, float]]:
        positions = {}
        for vertex_id in self.graph.vertices:
            position = self.graph_scene.vertex_position(vertex_id)
            positions[vertex_id] = (position.x(), position.y())
        return positions

    def graph_state(self) -> tuple:
        return self.graph.vertices, frozenset(self.graph.edges), self.graph_positions()

    def has_unsaved_changes(self) -> bool:
        return self.graph_state() != self._clean_state

    def mark_file_clean(self) -> None:
        self._clean_state = self.graph_state()
        # Undo can revisit this file after working on a different document.
        for index, (vertices, edges, positions, path, _, restore_path) in enumerate(self._undo_stack):
            if restore_path and path == self.current_file_path:
                self._undo_stack[index] = (vertices, edges, positions, path, self._clean_state, restore_path)

    def confirm_document_change(self, title_key: str, message_key: str | None = None) -> bool:
        if not self.has_unsaved_changes():
            return message_key is None or not self.graph.vertices or self.confirm_action(title_key, message_key)

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(self.localized_text(title_key))
        dialog.setText(self.localized_text("unsaved_graph"))
        buttons = QMessageBox.StandardButton
        dialog.setStandardButtons(buttons.Save | buttons.Discard | buttons.Cancel)
        dialog.setDefaultButton(buttons.Save)
        for button, key in ((buttons.Save, "save"), (buttons.Discard, "discard_changes"), (buttons.Cancel, "cancel")):
            dialog.button(button).setText(self.localized_text(key))

        try:
            choice = dialog.exec()
        finally:
            dialog.deleteLater()

        if self._external_shutdown:
            return False
        if choice == buttons.Save:
            return self.save_current_graph_as() if self.current_file_path is None else self.save_current_graph()
        return choice == buttons.Discard

    def closeEvent(self, event) -> None:
        if self._shutdown_ready:
            event.accept()
            return

        event.ignore()
        if self._shutdown_deadline is not None or self._close_prompt_active:
            return

        if not self._external_shutdown:
            self._close_prompt_active = True
            try:
                can_close = self.confirm_document_change("exit")
            finally:
                self._close_prompt_active = False
            if not can_close and not self._external_shutdown:
                return

        self.pause_playback()
        self.decision_timer.stop()
        self._deferred_calculation = None
        self._failures_at_shutdown = self._history_save_failures
        self._shutdown_deadline = monotonic() + SHUTDOWN_TIMEOUT_SECONDS
        self.setEnabled(False)
        self.background_timer.start()

    def request_shutdown(self) -> None:
        self._external_shutdown = True
        if self.has_unsaved_changes():
            logger.warning("Application stopped with unsaved graph changes")
        popup = QApplication.activePopupWidget()
        if popup is not None:
            popup.close()
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QDialog):
            dialog.reject()
        QTimer.singleShot(0, self.close)

    def poll_background_work(self) -> None:
        pending = []
        for result in self._calculation_saves:
            if not result.done():
                pending.append(result)
            elif not result.cancelled() and result.result():
                self._history_saved = True
            else:
                self._history_save_failures += 1
        self._calculation_saves = pending
        self.render_history_save_status()

        if self._shutdown_deadline is None:
            data = self._deferred_calculation
            if data is not None and not (QApplication.activeModalWidget() or QApplication.activePopupWidget()):
                self._deferred_calculation = None
                self.restore_history_calculation(data)
            if not self._calculation_saves and self._deferred_calculation is None:
                self.background_timer.stop()
            return

        if pending and monotonic() >= self._shutdown_deadline:
            for result in pending:
                result.cancel()
            self._history_save_unknown += len(pending)
            logger.warning("Closing without confirmation for %d calculation(s)", len(pending))
            self._calculation_saves = []
            self.render_history_save_status()

        if self._calculation_saves or any((self.history_loader, self.calculation_loader, self.events_loader)):
            return

        self.background_timer.stop()
        self._shutdown_ready = True
        failures = self._history_save_failures - self._failures_at_shutdown
        if (failures or self._history_save_unknown) and not self._external_shutdown:
            QMessageBox.warning(self, self.localized_text("exit"), self.history_save_status.text())
        QTimer.singleShot(0, self.close)

    def render_history_save_status(self) -> None:
        messages = []
        if self._calculation_saves:
            messages.append(self.localized_text("history_save_pending", count=len(self._calculation_saves)))
        if self._history_save_failures:
            messages.append(self.localized_text("history_save_failed", count=self._history_save_failures))
        if self._history_save_unknown:
            messages.append(self.localized_text("history_save_unconfirmed", count=self._history_save_unknown))
        if not messages and self._history_saved:
            messages.append(self.localized_text("history_save_success"))
        self.history_save_status.setText(" · ".join(messages))

    def on_algorithm_changed(self, algorithm: str) -> None:
        self.invalidate_mst()
        self.statusBar().showMessage(self.localized_text("algorithm_selected", algorithm=algorithm))

    def add_vertex_at(self, pos: QPointF) -> None:
        if not self.graph_scene.contains_vertex_position(pos):
            self.statusBar().showMessage(self.localized_text("vertex_out_of_bounds"))
            return
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
            1.0, -float_info.max, float_info.max, 2
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

        if not self.confirm_document_change("clear_canvas_title", "clear_canvas_question"):
            return

        self.save_undo(restore_file_path=True)

        self.current_file_path = None
        self.graph = Graph()
        self.graph_scene.clear_graph()
        self.pending_vertex = None
        self.graphView.resetTransform()
        self._clean_state = self.graph_state()

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
        self.clear_vertex_selection()
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
        self.clear_vertex_selection()

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
        self.clear_vertex_selection()

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

        self.clear_vertex_selection()

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
        self.progressSteps.setVisible(bool(steps))
        self.progressSteps.setRange(0, len(steps))
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
            self.decision_timer.stop()
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
        state = (tuple(sorted(self.graph.vertices)), self.graph.edges, self.graph_positions(),
                 self.current_file_path, self._clean_state, restore_file_path)
        self._undo_stack.append(state)

        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def undo(self) -> None:
        if not self._undo_stack:
            self.statusBar().showMessage(self.localized_text("nothing_to_undo"))
            return

        vertices, edges, positions, file_path, clean_state, restore_file_path = self._undo_stack.pop()
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

        if restore_file_path and (file_path is None or file_path != self.current_file_path):
            self.current_file_path = file_path
            self._clean_state = clean_state

        self.refresh_tables()
        self.statusBar().showMessage(self.localized_text("last_action_undone"))

    def begin_vertex_move(self) -> None:
        self.save_undo()
        self.invalidate_mst()

    def clear_vertex_selection(self) -> None:
        self.pending_vertex = None
        self.graph_scene.select_vertex(None)

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

        self.graph_scene.select_vertex(self.pending_vertex)
        self.refresh_tables()

    def show_vertex_menu(self, vertex_id: int, pos: QPoint) -> None:
        menu = QMenu(self)
        delete_action = menu.addAction(self.localized_text("vertex_delete_action"))

        try:
            action = menu.exec(pos)
        finally:
            menu.deleteLater()

        if action != delete_action:
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

        try:
            action = menu.exec(pos)
        finally:
            menu.deleteLater()

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

            text, ok = QInputDialog.getText(
                self, self.localized_text("change_weight_title"),
                self.localized_text("change_weight_prompt", start=start, end=end), text=str(edge.weight)
            )

            if not ok:
                return
            weight = self.parse_weight(text)
            if weight is None or weight == edge.weight:
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
                else:
                    item.setData(Qt.ItemDataRole.UserRole, pos.x() if column == 1 else pos.y())

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
                else:
                    item.setData(Qt.ItemDataRole.UserRole, edge.weight)

                self.tableEdges.setItem(row, column, item)


        self.tableEdges.blockSignals(False)

    def parse_weight(self, text: str) -> float | None:
        try:
            weight = float(text.replace(",", "."))
            if isfinite(weight):
                return weight
        except ValueError:
            pass
        QMessageBox.warning(self, self.localized_text("error_title"), self.localized_text("invalid_weight"))
        return None

    def on_edge_table_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 2:
            return

        row = item.row()
        start = int(self.tableEdges.item(row, 0).text())
        end = int(self.tableEdges.item(row, 1).text())

        edge = next(e for e in self.graph.edges if e.start == start and e.end == end)

        weight = self.parse_weight(item.text())
        if weight is None or weight == edge.weight:
            self.refresh_tables()
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
            1.0, -float_info.max, float_info.max, 2
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

        old_pos = self.graph_scene.vertex_position(vertex_id)
        try:
            value = float(item.text().replace(",", "."))
            if not isfinite(value):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, self.localized_text("invalid_coord_title"), self.localized_text("invalid_coords"))
            self.refresh_tables()
            return

        new_pos = QPointF(value, old_pos.y()) if item.column() == 1 else QPointF(old_pos.x(), value)

        if new_pos == old_pos:
            self.refresh_tables()
            return

        if not self.graph_scene.contains_vertex_position(new_pos):
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

        try:
            new_graph = generate_random_graph(vertex_count, edge_count, min_weight, max_weight)
        except GraphError as error:
            QMessageBox.warning(self, self.localized_text("generation_error_title"), self.localized_error(error))
            return

        if not self.confirm_document_change("generate_graph_title", "replace_graph_prompt"):
            return

        self.save_undo(restore_file_path=True)
        self.invalidate_mst()
        self.pending_vertex = None
        self.current_file_path = None
        self._clean_state = (frozenset(), frozenset(), {})

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

    def write_graph_to_file(self, path: Path) -> bool:
        try:
            save_graph(self.graph, self.graph_positions(), path)
        except GraphError as error:
            QMessageBox.critical(
                self, self.localized_text("save_error_title"), self.localized_error(error)
            )
            return False
        except (OSError, ValueError):
            logger.exception("Could not write graph file")
            QMessageBox.critical(self, self.localized_text("save_error_title"), self.localized_text("graph_write_error"))
            return False

        self.current_file_path = path
        self.mark_file_clean()
        self.statusBar().showMessage(self.localized_text("graph_saved", filename=path.name))
        return True

    def save_current_graph(self) -> bool:
        if self.current_file_path is not None:
            return self.write_graph_to_file(self.current_file_path)

        index = 1

        while True:
            path = self.graphs_dir / f"graph_{index:03d}.json"

            if not path.exists():
                break

            index += 1

        return self.write_graph_to_file(path)

    def save_current_graph_as(self) -> bool:
        suggested_path = (
                self.current_file_path
                or self.graphs_dir / "graph.json"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self,
            self.localized_text("save_graph_as_title"),
            str(suggested_path),
            self.localized_text("graph_files_filter")
        )

        if not filename:
            return False

        path = Path(filename)

        if path.suffix.lower() != ".json":
            path = Path(str(path) + ".json")

        return self.write_graph_to_file(path)

    def validate_graph_positions(self, positions: dict[int, tuple[float, float]]) -> None:
        checked = {}
        for vertex_id, position in positions.items():
            point = QPointF(*position)
            if not self.graph_scene.contains_vertex_position(point):
                raise GraphError("Вершина находится за пределами полотна",
                                 code="loaded_vertex_out_of_bounds", vertex_id=vertex_id)
            for other_id, other_point in checked.items():
                if not self.graph_scene.vertices_are_separated(point, other_point):
                    raise GraphError("Вершины слишком близко", code="loaded_vertices_too_close",
                                     first=other_id, second=vertex_id)
            checked[vertex_id] = point

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
            self.validate_graph_positions(positions)
        except GraphError as error:
            QMessageBox.warning(self, self.localized_text("load_error_title"), self.localized_error(error))
            return
        except (OSError, ValueError):
            logger.exception("Could not read graph file")
            QMessageBox.critical(self, self.localized_text("load_error_title"), self.localized_text("graph_read_error"))
            return

        if not self.confirm_document_change("load_graph_title", "replace_graph_prompt"):
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
        self.mark_file_clean()

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

        icons_dir = Path(__file__).resolve().parents[2] / "assets"
        stylesheet = stylesheet.replace("__SPIN_UP__", (icons_dir / f"spin-up-{theme}.svg").as_posix())
        stylesheet = stylesheet.replace("__SPIN_DOWN__", (icons_dir / f"spin-down-{theme}.svg").as_posix())

        QApplication.instance().setStyleSheet(stylesheet)

    def update_language(self) -> None:
        lang = self.language

        # Главное меню и панель управления
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

        # Кнопки и подписи
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
            (self.btnRefreshHistory, "history_refresh"),
            (self.labelEventLevel, "events_level_filter"),
            (self.btnRefreshEvents, "events_refresh"),
        ]

        for widget, key in widgets:
            widget.setText(translate(key, lang))

        # Названия вкладок
        tabs = [
            (self.tabCanvas, "canvas"),
            (self.tabTables, "tables"),
            (self.tabHistory, "history_tab"),
            (self.tabEvents, "events_tab"),
        ]

        for tab, key in tabs:
            self.tabGraphEditor.setTabText(
                self.tabGraphEditor.indexOf(tab),
                translate(key, lang)
            )

        # Заголовки таблиц
        self.tableEdges.setHorizontalHeaderLabels([
            translate("start", lang),
            translate("end", lang),
            translate("weight", lang)
        ])

        self.tableHistory.setHorizontalHeaderLabels([
            "ID",
            translate("history_date", lang),
            translate("history_algorithm", lang),
            translate("history_mode", lang),
            translate("history_vertices", lang),
            translate("history_edges", lang),
            translate("history_weight", lang),
            translate("history_time", lang)
        ])

        self.tableEvents.setHorizontalHeaderLabels([
            "ID",
            translate("events_date", lang),
            translate("events_level", lang),
            translate("events_source", lang),
            translate("events_code", lang),
            translate("events_message", lang),
            translate("events_calculation", lang)
        ])

        self.comboEventLevel.setItemText(0, translate("events_all", lang))

        # Выбор алгоритма
        self.comboAlgorithm.blockSignals(True)
        self.comboAlgorithm.setItemText(0, translate("kruskal", lang))
        self.comboAlgorithm.setItemText(1, translate("prim", lang))
        self.comboAlgorithm.blockSignals(False)

        # Пошаговое воспроизведение
        playback_key = "pause" if self.playback_timer.isActive() else "play"
        self.btnPlayPause.setText(translate(playback_key, lang))
        self.progressSteps.setFormat(translate("step_progress", lang))

        # Обновление результатов
        self.update_result_labels(preview=self.decision_timer.isActive())
        self.render_history_save_status()

        self.render_event_logs()

        if self.history_records:
            self.show_history(self.history_records)

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
        data = {
            "algorithm": "kruskal" if algorithm_index == 0 else "prim",
            "run_mode": run_mode,
            "vertex_count": len(self.graph.vertices),
            "edge_count": len(self.graph.edges),
            "graph_data": graph_to_dict(self.graph, self.graph_positions()),
            "result_edges": [edge_to_dict(edge) for edge in result.edges],
            "steps": [{"edge": edge_to_dict(step.edge), "accepted": step.accepted} for step in result.steps],
            "total_weight": result.total_weight,
            "duration_ms": self.execution_time_ms
        }

        self._calculation_saves.append(queue_calculation(data))
        self.background_timer.start()
        self.render_history_save_status()

    def load_history(self) -> None:
        if self.history_loader is not None or self._shutdown_deadline is not None:
            return

        self.btnRefreshHistory.setEnabled(False)

        self.history_loader = CalculationsLoader(self)
        self.history_loader.loaded.connect(self.show_history)
        self.history_loader.failed.connect(self.history_load_failed)
        self.history_loader.finished.connect(self.history_load_finished)
        self.history_loader.start()

    def show_history(self, calculations: list[dict]) -> None:
        self.history_records = calculations

        self.tableHistory.setSortingEnabled(False)
        self.tableHistory.setRowCount(len(calculations))

        for row, calculation in enumerate(calculations):
            algorithm_key = calculation["algorithm"]
            algorithm = self.localized_text(algorithm_key) if algorithm_key in ("kruskal", "prim") else algorithm_key
            mode_key = calculation["run_mode"]
            mode = self.localized_text(f"history_mode_{mode_key}") if mode_key in ("build", "step") else mode_key

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
            sort_keys = {0: calculation["id"], 1: calculation["created_at"],
                         4: calculation["vertex_count"], 5: calculation["edge_count"],
                         6: calculation["total_weight"], 7: calculation["duration_ms"]}

            for column, value in enumerate(values):
                item = SortableTableItem(str(value))
                if column in sort_keys:
                    item.setData(Qt.ItemDataRole.UserRole, sort_keys[column])
                self.tableHistory.setItem(row, column, item)

        self.tableHistory.setSortingEnabled(True)
        self.statusBar().showMessage(self.localized_text("history_loaded_count", count=len(calculations)))

    def history_load_failed(self) -> None:
        self.statusBar().showMessage(self.localized_text("history_list_load_error"))

    def history_load_finished(self) -> None:
        self.btnRefreshHistory.setEnabled(True)
        self.history_loader.deleteLater()
        self.history_loader = None

    def open_history_calculation(self, row: int, column: int) -> None:
        if self.calculation_loader is not None or self._deferred_calculation is not None or self._shutdown_deadline is not None:
            return

        item = self.tableHistory.item(row, 0)
        if item is None:
            return

        calculation_id = item.data(Qt.ItemDataRole.UserRole)

        self.calculation_loader = CalculationDetailsLoader(calculation_id, self)
        self.calculation_loader.loaded.connect(self.restore_history_calculation)
        self.calculation_loader.failed.connect(self.calculation_load_failed)
        self.calculation_loader.missing.connect(self.calculation_not_found)
        self.calculation_loader.finished.connect(self.calculation_load_finished)
        self.calculation_loader.start()

    def calculation_load_failed(self) -> None:
        self.statusBar().showMessage(self.localized_text("history_load_error"))

    def calculation_not_found(self) -> None:
        self.statusBar().showMessage(self.localized_text("history_not_found"))

    def calculation_load_finished(self) -> None:
        self.calculation_loader.deleteLater()
        self.calculation_loader = None

    def restore_history_calculation(self, data: dict) -> None:
        if self._external_shutdown or self._shutdown_deadline is not None:
            return
        if QApplication.activeModalWidget() or QApplication.activePopupWidget():
            self._deferred_calculation = data
            self.background_timer.start()
            return

        try:
            new_graph, positions, result = decode_calculation(data)
            self.validate_graph_positions(positions)
        except GraphError as error:
            QMessageBox.warning(self, self.localized_text("history_open_error"), self.localized_error(error))
            return

        except ValueError:
            logger.warning("Invalid calculation history", exc_info=True)
            QMessageBox.warning(self, self.localized_text("history_open_error"), self.localized_text("history_invalid"))
            return

        if not self.confirm_document_change("load_graph_title", "replace_graph_prompt"):
            return

        self.save_undo(restore_file_path=True)
        self.invalidate_mst()
        self.pending_vertex = None
        self.current_file_path = None

        self.graph = new_graph
        self.graph_scene.clear_graph()
        self.graphView.resetTransform()

        for vertex_id, (x, y) in sorted(positions.items()):
            self.graph_scene.add_vertex(vertex_id, QPointF(x, y))

        for edge in self.graph.edges:
            self.graph_scene.add_edge(edge.start, edge.end, edge.weight)

        self._clean_state = self.graph_state()
        self.comboAlgorithm.blockSignals(True)
        self.comboAlgorithm.setCurrentIndex(0 if data["algorithm"] == "kruskal" else 1)
        self.comboAlgorithm.blockSignals(False)

        self.last_result = result
        self.execution_time_ms = data["duration_ms"]
        self.btnShowOriginalGraph.setEnabled(True)

        if data["run_mode"] == "step":
            self.step_index = 0
            self.update_step_view()
        else:
            self.step_index = None
            self.graph_scene.show_mst(result.edges)
            self.progressSteps.setVisible(False)
            self.update_result_labels()

        self.refresh_tables()
        self.tabGraphEditor.setCurrentWidget(self.tabCanvas)
        self.statusBar().showMessage(self.localized_text("history_opened", id=data["id"]))

        record_event("INFO", "history", "history.opened", "Calculation opened from history", calculation_id=data["id"])

    def load_event_logs(self) -> None:
        if self.events_loader is not None or self._shutdown_deadline is not None:
            return

        self.btnRefreshEvents.setEnabled(False)

        self.events_loader = EventLogsLoader(self)
        self.events_loader.loaded.connect(self.event_logs_loaded)
        self.events_loader.failed.connect(self.event_logs_failed)
        self.events_loader.finished.connect(self.event_logs_finished)
        self.events_loader.start()

    def event_logs_loaded(self, events: list[dict]) -> None:
        self.events_records = events
        self.render_event_logs()
        self.statusBar().showMessage(self.localized_text("events_loaded", count=len(events)))

    def event_logs_failed(self) -> None:
        self.statusBar().showMessage(self.localized_text("events_load_error"))

    def event_logs_finished(self) -> None:
        self.btnRefreshEvents.setEnabled(True)
        self.events_loader.deleteLater()
        self.events_loader = None

    def render_event_logs(self) -> None:
        selected_level = self.comboEventLevel.currentData()

        if selected_level is None:
            events = self.events_records
        else:
            events = [event for event in self.events_records if event["level"] == selected_level]

        self.tableEvents.setSortingEnabled(False)
        self.tableEvents.setRowCount(len(events))

        for row, event in enumerate(events):
            date = event["created_at"].strftime("%d.%m.%Y %H:%M:%S")
            values = [
                event["id"],
                date,
                event["level"],
                event["source"],
                event["event_code"],
                event["message"],
                event.get("calculation_id") or ""
            ]

            for column, value in enumerate(values):
                item = SortableTableItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, event["id"])
                elif column == 1:
                    item.setData(Qt.ItemDataRole.UserRole, event["created_at"])
                elif column == 6:
                    item.setData(Qt.ItemDataRole.UserRole, event.get("calculation_id") or 0)
                self.tableEvents.setItem(row, column, item)

                if column == 5 and event.get("details"):
                    item.setToolTip(json.dumps(event["details"], ensure_ascii=False, indent=2, default=str))

        self.tableEvents.setSortingEnabled(True)


