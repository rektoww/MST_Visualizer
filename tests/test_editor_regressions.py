import os
from concurrent.futures import Future
from datetime import datetime, timezone
from threading import Event
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit

import app.views.main_window as ui
from app.core.graph_storage import load_graph


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def window(qt_app, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "QSettings", lambda *args: SimpleNamespace(value=lambda key, default: default))
    monkeypatch.delenv("MST_GRAPH_DIR", raising=False)
    monkeypatch.setattr(ui, "record_event", lambda *args, **kwargs: None)
    window = ui.MainWindow()
    window.graphs_dir = tmp_path
    window.language = "en"
    window.update_language()
    window.warnings = []
    for name in ("warning", "critical"):
        monkeypatch.setattr(ui.QMessageBox, name, lambda parent, title, message: window.warnings.append(message))
    yield window
    window._shutdown_ready = True
    window.background_timer.stop()
    window.invalidate_mst()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def add_edge(window, weight=1.23456789):
    window.add_vertex_at(QPointF(100, 100.04))
    window.add_vertex_at(QPointF(220, 100))
    window.graph.add_edge(1, 2, weight)
    window.rebuild_scene()


@pytest.mark.parametrize("position", [(5, 5), (0, 0), (1200, 900)])
def test_create_save_open_at_canvas_edge(window, monkeypatch, position):
    point = QPointF(*position)
    window.add_vertex_at(point)
    assert window.graph_scene.can_place_vertex(point, 1)
    assert window.save_current_graph()
    path = window.current_file_path
    monkeypatch.setattr(ui.QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(window, "confirm_action", lambda *args: True)

    window.load_graph_from_file()

    assert window.graph_scene.vertex_position(1) == point
    assert not window.warnings
    assert not window.has_unsaved_changes()


def test_canvas_rejects_outside_and_keeps_legacy_coordinates(window, monkeypatch, tmp_path):
    window.add_vertex_at(QPointF(-0.1, 100))
    window.add_vertex_at(QPointF(100, 900.1))
    assert not window.graph.vertices
    path = tmp_path / "legacy.json"
    path.write_text('{"version":1,"vertices":[{"id":9,"x":5,"y":5}],"edges":[]}', encoding="utf-8")
    monkeypatch.setattr(ui.QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    window.load_graph_from_file()
    assert window.graph_positions() == {9: (5, 5)}


def test_canvas_drag_uses_same_bounds_and_undo(window):
    window.show()
    window.add_vertex_at(QPointF(60, 60))
    viewport = window.graphView.viewport()
    start = window.graphView.mapFromScene(QPointF(60, 60))
    end = window.graphView.mapFromScene(QPointF(5, 5))
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(viewport, end)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)
    assert window.graph_positions() == {1: (5, 5)}
    window.undo()
    assert window.graph_positions() == {1: (60, 60)}


def test_table_preserves_exact_values_through_undo_and_storage(window, monkeypatch):
    add_edge(window)
    assert window.save_current_graph()
    path = window.current_file_path

    window.tableVertices.item(0, 1).setText("110.0123")
    assert window.graph_positions()[1] == (110.0123, 100.04)
    window.tableEdges.item(0, 2).setText("0.123456789123")
    assert window.graph.edges[0].weight == 0.123456789123
    assert window.has_unsaved_changes()

    window.undo()
    assert window.graph.edges[0].weight == 1.23456789
    window.undo()
    assert not window.has_unsaved_changes()

    window.tableVertices.item(0, 1).setText("110.0123")
    assert window.save_current_graph()
    monkeypatch.setattr(ui.QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(window, "confirm_action", lambda *args: True)
    window.load_graph_from_file()
    assert window.graph_positions()[1] == (110.0123, 100.04)
    assert window.graph.edges[0].weight == 1.23456789


def test_table_editor_starts_with_unrounded_weight(window):
    add_edge(window)
    item = window.tableEdges.item(0, 2)
    assert item.text() == "1.23457"
    editor = QLineEdit()
    index = window.tableEdges.model().index(0, 2)
    window.tableEdges.itemDelegate().setEditorData(editor, index)
    assert editor.text() == "1.23456789"


def test_weight_edit_clears_internal_and_visible_selection(window):
    add_edge(window)
    window.on_vertex_clicked(1)
    window.tableEdges.item(0, 2).setText("3")

    assert window.pending_vertex is None
    assert window.graph_scene._vertex_items[1].pen().color() == Qt.GlobalColor.black
    window.on_vertex_clicked(2)
    assert window.pending_vertex == 2
    assert window.graph_scene._vertex_items[2].pen().color() == Qt.GlobalColor.yellow
    window.undo()
    assert window.pending_vertex is None


def test_large_ids_reach_scene_handlers_intact(window, monkeypatch, tmp_path):
    vertex_id = 2**70
    path = tmp_path / "large-id.json"
    path.write_text(f'{{"version":1,"vertices":[{{"id":{vertex_id},"x":100,"y":100}}],"edges":[]}}',
                    encoding="utf-8")
    monkeypatch.setattr(ui.QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    window.load_graph_from_file()
    window.show()
    point = window.graphView.mapFromScene(QPointF(100, 100))
    QTest.mouseClick(window.graphView.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert window.pending_vertex == vertex_id


def test_dirty_close_cancel_then_save_as(window, monkeypatch, tmp_path):
    window.show()
    window.add_vertex_at(QPointF(100, 100))
    buttons = ui.QMessageBox.StandardButton
    monkeypatch.setattr(ui.QMessageBox, "exec", lambda dialog: buttons.Save)
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", lambda *args: ("", ""))

    window.close()
    assert window.isVisible()
    assert window.has_unsaved_changes()

    path = tmp_path / "keep.json"
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", lambda *args: (str(path), ""))
    window.close()
    QTest.qWait(180)
    assert not window.isVisible()
    assert load_graph(path)[0].vertices == {1}
    assert not window.has_unsaved_changes()


def test_failed_save_keeps_dirty_document_and_previous_file(window, monkeypatch, tmp_path):
    window.add_vertex_at(QPointF(100, 100))
    assert window.save_current_graph()
    original = window.current_file_path
    old_bytes = original.read_bytes()
    window.add_vertex_at(QPointF(200, 100))

    def fail_replace(source, destination):
        raise PermissionError("read only")

    monkeypatch.setattr("app.core.graph_storage.os.replace", fail_replace)
    monkeypatch.setattr(ui.QMessageBox, "exec", lambda dialog: ui.QMessageBox.StandardButton.Save)
    window.show()
    window.close()
    window.clear_canvas()
    assert window.isVisible()
    assert window.has_unsaved_changes()
    assert window.graph.vertices == {1, 2}
    assert original.read_bytes() == old_bytes

    target = tmp_path / "save-as.json"
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    assert not window.save_current_graph_as()
    assert not target.exists()
    assert window.current_file_path == original
    assert not list(tmp_path.glob("*.tmp"))


def test_document_replacement_prompts_once_and_undo_restores_dirty_state(window, monkeypatch):
    add_edge(window)
    undo_count = len(window._undo_stack)
    buttons = ui.QMessageBox.StandardButton
    prompts = []

    def discard(dialog):
        prompts.append(dialog.text())
        return buttons.Discard

    monkeypatch.setattr(ui.QMessageBox, "exec", discard)
    window.clear_canvas()
    assert len(prompts) == 1
    assert not window.graph.vertices
    assert not window.has_unsaved_changes()
    assert len(window._undo_stack) == undo_count + 1
    window.undo()
    assert window.graph.vertices == {1, 2}
    assert window.has_unsaved_changes()


def test_undo_revisiting_a_file_compares_against_its_last_saved_version(window, monkeypatch, tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    window.add_vertex_at(QPointF(100, 100))
    assert window.write_graph_to_file(first)
    monkeypatch.setattr(window, "confirm_action", lambda *args: True)
    window.clear_canvas()
    window.add_vertex_at(QPointF(300, 100))
    assert window.write_graph_to_file(second)

    monkeypatch.setattr(ui.QFileDialog, "getOpenFileName", lambda *args: (str(first), ""))
    window.load_graph_from_file()
    window.add_vertex_at(QPointF(200, 100))
    assert window.save_current_graph()
    assert not window.has_unsaved_changes()

    window.undo()
    assert window.has_unsaved_changes()
    window.undo()
    assert window.current_file_path == second
    assert not window.has_unsaved_changes()
    window.undo()
    window.undo()
    assert window.current_file_path == first
    assert window.graph.vertices == {1}
    assert window.has_unsaved_changes()


def queue_to_future(monkeypatch, future=None):
    if future is None:
        future = Future()
        future.set_result(True)
    monkeypatch.setattr(ui, "queue_calculation", lambda data: future)
    return future


def test_step_replay_stops_old_preview_and_algorithm_switch_stops_both(window, monkeypatch):
    add_edge(window)
    assert window.save_current_graph()
    queue_to_future(monkeypatch)
    window.comboAlgorithm.setCurrentIndex(0)
    window.start_step_mode()
    window.next_step()
    assert window.step_index == 1
    assert window.decision_timer.isActive()
    assert not window.btnNextStep.isEnabled()

    window.toggle_playback()
    assert window.step_index == 0
    assert not window.decision_timer.isActive()
    assert window.playback_timer.isActive()
    window.next_step()
    window.previous_step()
    assert window.step_index == 0
    assert not window.decision_timer.isActive()
    assert not window.playback_timer.isActive()
    window.toggle_playback()
    window.comboAlgorithm.setCurrentIndex(1)
    assert not window.decision_timer.isActive()
    assert not window.playback_timer.isActive()
    assert window.last_result is None
    assert not window.has_unsaved_changes()


def test_no_progress_or_playback_for_single_vertex(window, monkeypatch):
    queue_to_future(monkeypatch)
    window.show()
    window.add_vertex_at(QPointF(100, 100))
    window.comboAlgorithm.setCurrentIndex(0)
    window.start_step_mode()
    assert window.progressSteps.isHidden()
    assert not window.btnNextStep.isEnabled()
    assert not window.btnPreviousStep.isEnabled()
    assert not window.btnPlayPause.isEnabled()


def test_context_menus_are_released(window, monkeypatch):
    add_edge(window)
    count = len(window.findChildren(ui.QMenu))
    monkeypatch.setattr(ui.QMenu, "exec", lambda *args: None)
    for _ in range(5):
        window.show_vertex_menu(1, window.pos())
        window.show_edge_menu(1, 2, window.pos())
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert len(window.findChildren(ui.QMenu)) == count


def test_history_and_event_sorting_keeps_numeric_ids_and_dates(window, monkeypatch):
    newer = datetime(2026, 2, 1, tzinfo=timezone.utc)
    older = datetime(2026, 1, 31, tzinfo=timezone.utc)
    records = [
        dict(id=10, created_at=older, algorithm="prim", run_mode="step", vertex_count=2,
             edge_count=1, total_weight=1, duration_ms=2),
        dict(id=2, created_at=newer, algorithm="kruskal", run_mode="build", vertex_count=2,
             edge_count=1, total_weight=2, duration_ms=3),
    ]
    window.show_history(records)
    window.event_logs_loaded([dict(id=row["id"], created_at=row["created_at"], level="INFO",
                                   source="app", event_code="started", message="started") for row in records])
    for table in (window.tableHistory, window.tableEvents):
        table.sortItems(0, Qt.SortOrder.AscendingOrder)
        assert [table.item(i, 0).text() for i in range(2)] == ["2", "10"]
        table.sortItems(1, Qt.SortOrder.AscendingOrder)
        assert [table.item(i, 0).text() for i in range(2)] == ["10", "2"]

    requested = []
    monkeypatch.setattr("app.views.calculations_loader.get_calculation_by_id",
                        lambda key: requested.append(key))
    window.tableHistory.cellDoubleClicked.emit(0, 4)
    QTest.qWait(100)
    assert requested == [10]
    assert window.calculation_loader is None
    assert window.statusBar().currentMessage() == window.localized_text("history_not_found")


def test_shutdown_waits_asynchronously_and_reports_failed_write(window, monkeypatch):
    add_edge(window)
    assert window.save_current_graph()
    window.show()
    pending = queue_to_future(monkeypatch, Future())
    window.comboAlgorithm.setCurrentIndex(0)
    window.build_mst()
    assert window.localized_text("history_save_pending", count=1) in window.history_save_status.text()
    assert not window.has_unsaved_changes()

    window.close()
    QTest.qWait(150)
    assert window.isVisible()
    pending.set_result(False)
    QTest.qWait(180)
    assert not window.isVisible()
    assert window.warnings == [window.localized_text("history_save_failed", count=1)]


def test_shutdown_deadline_labels_unconfirmed_saves(window, monkeypatch):
    add_edge(window)
    assert window.save_current_graph()
    window.show()
    pending = queue_to_future(monkeypatch, Future())
    monkeypatch.setattr(ui, "SHUTDOWN_TIMEOUT_SECONDS", 0)
    window.comboAlgorithm.setCurrentIndex(0)
    window.build_mst()
    window.close()
    QTest.qWait(180)
    assert pending.cancelled()
    assert not window.isVisible()
    assert window.warnings == [window.localized_text("history_save_unconfirmed", count=1)]


def test_shutdown_keeps_qt_alive_until_history_loader_finishes(window, monkeypatch):
    started, release = Event(), Event()

    def delayed_read(limit):
        started.set()
        assert release.wait(2)
        return []

    monkeypatch.setattr("app.views.calculations_loader.get_calculations", delayed_read)
    window.show()
    window.load_history()
    try:
        assert started.wait(1)
        window.close()
        QTest.qWait(120)
        assert window.isVisible()
        assert window.history_loader.isRunning()
    finally:
        release.set()
    QTest.qWait(250)
    assert window.history_loader is None
    assert not window.isVisible()


def test_history_application_waits_for_modal_editor(window, monkeypatch):
    received = []
    dialog = QDialog(window)
    dialog.setModal(True)
    dialog.show()
    window.restore_history_calculation({"id": 1})
    assert not window.warnings
    assert window._deferred_calculation == {"id": 1}
    monkeypatch.setattr(window, "restore_history_calculation", received.append)
    dialog.close()
    window.poll_background_work()
    assert received == [{"id": 1}]


@pytest.mark.parametrize("algorithm_index,mode", [(0, "build"), (0, "step"), (1, "build"), (1, "step")])
def test_history_restores_valid_payload_and_preserves_document_on_failure(window, monkeypatch, algorithm_index, mode):
    sent = []
    future = Future()
    future.set_result(True)

    def save(data):
        sent.append(data)
        return future

    monkeypatch.setattr(ui, "queue_calculation", save)
    add_edge(window, -2.5)
    assert window.save_current_graph()
    window.comboAlgorithm.setCurrentIndex(algorithm_index)
    (window.build_mst if mode == "build" else window.start_step_mode)()
    data = dict(sent[-1], id=12)
    monkeypatch.setattr(window, "confirm_action", lambda *args: True)
    window.restore_history_calculation(data)
    assert window.last_result.total_weight == -2.5
    assert window.step_index == (0 if mode == "step" else None)
    assert not window.has_unsaved_changes()

    old_graph, old_result, old_steps = window.graph, window.last_result, list(window._undo_stack)
    data["steps"][0]["edge"]["end"] = 99
    window.restore_history_calculation(data)
    assert window.warnings == [window.localized_text("history_invalid")]
    assert window.graph is old_graph
    assert window.last_result is old_result
    assert window._undo_stack == old_steps
