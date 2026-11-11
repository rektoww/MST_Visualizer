from PyQt6.QtCore import Qt, QPointF, QLineF, pyqtSignal, QRectF, QPoint
from PyQt6.QtGui import QBrush, QPen, QTransform, QColor, QFont, QPainterPath
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsSceneMouseEvent, QGraphicsTextItem, QGraphicsPathItem
from app.core.edge import Edge
from app.core.algorithms.result import AlgorithmStep


class GraphScene(QGraphicsScene):
    MIN_VERTEX_DISTANCE = 50

    empty_space_clicked = pyqtSignal(QPointF)
    vertex_clicked = pyqtSignal(int)
    vertex_move_started = pyqtSignal()
    vertex_moved = pyqtSignal(int)
    vertex_context_requested = pyqtSignal(int, QPoint)
    edge_context_requested = pyqtSignal(int, int, QPoint)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._vertex_items = {}
        self._edge_items = {}
        self._pressed_vertex = None
        self._press_pos = None
        self._vertex_start_pos = None
        self._dragging = False
        self._vertex_changed = False

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        item = self.itemAt(event.scenePos(), QTransform())

        if event.button() == Qt.MouseButton.LeftButton:
            if item is None:
                self.empty_space_clicked.emit(event.scenePos())
                event.accept()
                return

            while item is not None:
                vertex_id = item.data(0)

                if vertex_id is not None:
                    self._pressed_vertex = vertex_id
                    self._press_pos = QPointF(event.scenePos())
                    self._vertex_start_pos = QPointF(self._vertex_items[vertex_id].pos())
                    self._dragging = False
                    self._vertex_changed = False
                    event.accept()
                    return

                item = item.parentItem()

        elif event.button() == Qt.MouseButton.RightButton:
            while item is not None:
                vertex_id = item.data(0)
                edge_key = item.data(1)

                if vertex_id is not None:
                    self.vertex_context_requested.emit(vertex_id, event.screenPos())
                    event.accept()
                    return

                if edge_key is not None:
                    self.edge_context_requested.emit(*edge_key, event.screenPos())
                    event.accept()
                    return

                item = item.parentItem()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._pressed_vertex is None:
            super().mouseMoveEvent(event)
            return

        distance = QLineF(self._press_pos, event.scenePos()).length()

        if not self._dragging and distance < 5:
            event.accept()
            return

        self._dragging = True

        new_pos = self._vertex_start_pos + event.scenePos() - self._press_pos

        if not self.sceneRect().adjusted(18, 18, -18, -18).contains(new_pos):
            event.accept()
            return

        if not self.can_place_vertex(new_pos, self._pressed_vertex):
            event.accept()
            return

        circle = self._vertex_items[self._pressed_vertex]

        if new_pos != circle.pos():
            if not self._vertex_changed:
                self.vertex_move_started.emit()
                self._vertex_changed = True

            circle.setPos(new_pos)
            self.update_connected_edges(self._pressed_vertex)

        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed_vertex is not None:
            vertex_id = self._pressed_vertex

            if not self._dragging:
                self.vertex_clicked.emit(vertex_id)
            elif self._vertex_changed:
                self.vertex_moved.emit(vertex_id)

            self._pressed_vertex = None
            self._press_pos = None
            self._vertex_start_pos = None
            self._dragging = False
            self._vertex_changed = False

            event.accept()
            return

        super().mouseReleaseEvent(event)

    def add_vertex(self, vertex_id: int, pos: QPointF) -> None:
        radius = 18

        circle = self.addEllipse(-radius, -radius, radius * 2, radius * 2,
                                 QPen(Qt.GlobalColor.black), QBrush(Qt.GlobalColor.darkCyan))
        circle.setPos(pos)
        circle.setData(0, vertex_id)
        circle.setZValue(2)

        label = QGraphicsTextItem(str(vertex_id), circle)
        label.setDefaultTextColor(Qt.GlobalColor.white)

        rect = label.boundingRect()
        label.setPos(-rect.width() / 2, -rect.height() / 2)

        self._vertex_items[vertex_id] = circle

    def select_vertex(self, vertex_id: int | None) -> None:
        for current_id, circle in self._vertex_items.items():
            if current_id == vertex_id:
                circle.setPen(QPen(Qt.GlobalColor.yellow, 3))
            else:
                circle.setPen(QPen(Qt.GlobalColor.black, 1))

    def add_edge(self, start: int, end: int, weight: float) -> None:
        first_pos = self._vertex_items[start].pos()
        second_pos = self._vertex_items[end].pos()

        line = self.addLine(QLineF(first_pos, second_pos), QPen(Qt.GlobalColor.darkGray, 2))
        line.setZValue(-1)

        badge = QGraphicsPathItem()
        text = QGraphicsTextItem(f"{weight:g}", badge)

        font = QFont()
        font.setPointSize(11)
        font.setBold(True)

        text.setFont(font)
        text.setDefaultTextColor(QColor("#1f2937"))

        text_rect = text.boundingRect()
        width = text_rect.width() + 12
        height = text_rect.height() + 4

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, width, height), 6, 6)

        badge.setPath(path)
        badge.setBrush(QBrush(Qt.GlobalColor.white))
        badge.setPen(QPen(QColor("#cbd5e1"), 1))
        badge.setZValue(1)

        text.setPos((width - text_rect.width()) / 2, (height - text_rect.height()) / 2)

        center_x = (first_pos.x() + second_pos.x()) / 2
        center_y = (first_pos.y() + second_pos.y()) / 2

        badge.setPos(center_x - width / 2, center_y - height / 2)
        self.addItem(badge)

        first, second = sorted((start, end))
        self._edge_items[(first, second)] = (line, badge)

        line.setData(1, (first, second))
        badge.setData(1, (first, second))

    def can_place_vertex(self, pos: QPointF, exclude_vertex: int | None = None) -> bool:
        return all(
            QLineF(pos, circle.pos()).length() >= self.MIN_VERTEX_DISTANCE
            for vertex_id, circle in self._vertex_items.items()
            if vertex_id != exclude_vertex
        )

    def clear_graph(self) -> None:
        self.clear()
        self._vertex_items.clear()
        self._edge_items.clear()
        self._pressed_vertex = None
        self._press_pos = None
        self._vertex_start_pos = None
        self._dragging = False
        self._vertex_changed = False


    def show_mst(self, edges: tuple[Edge, ...]) -> None:
        selected = {(edge.start, edge.end) for edge in edges}

        for key, (line, badge) in self._edge_items.items():
            if key in selected:
                line.setPen(QPen(QColor("#16a34a"), 3))
                line.setOpacity(1.0)
                badge.setOpacity(1.0)
            else:
                line.setPen(QPen(QColor("#94a3b8"), 2))
                line.setOpacity(0.25)
                badge.setOpacity(0.25)

    def show_original_graph(self) -> None:
        for line, badge in self._edge_items.values():
            line.setPen(QPen(Qt.GlobalColor.darkGray, 2))
            line.setOpacity(1.0)
            badge.setOpacity(1.0)

    def show_algorithm_step(self, steps: tuple[AlgorithmStep, ...], count: int, preview: bool = False) -> None:
        for line, badge in self._edge_items.values():
            line.setPen(QPen(QColor("#94a3b8"), 2))
            line.setOpacity(0.3)
            badge.setOpacity(0.3)

        for index, step in enumerate(steps[:count]):
            key = tuple(sorted((step.edge.start, step.edge.end)))
            line, badge = self._edge_items[key]

            if preview and index == count - 1:
                color = "#f59e0b"
            elif step.accepted:
                color = "#16a34a"
            elif index == count - 1:
                color = "#dc2626"
            else:
                continue

            line.setPen(QPen(QColor(color), 3))
            line.setOpacity(1.0)
            badge.setOpacity(1.0)

    def update_connected_edges(self, vertex_id: int) -> None:
        for (start, end), (line, badge) in self._edge_items.items():
            if vertex_id not in (start, end):
                continue

            first_pos = self._vertex_items[start].pos()
            second_pos = self._vertex_items[end].pos()

            line.setLine(QLineF(first_pos, second_pos))

            center_x = (first_pos.x() + second_pos.x()) / 2
            center_y = (first_pos.y() + second_pos.y()) / 2

            rect = badge.path().boundingRect()
            badge.setPos(center_x - rect.width() / 2, center_y - rect.height() / 2)

    def vertex_position(self, vertex_id: int) -> QPointF:
        return QPointF(self._vertex_items[vertex_id].pos())
