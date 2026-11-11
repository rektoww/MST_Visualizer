from PyQt6.QtCore import Qt, QPointF, QLineF, pyqtSignal, QRectF
from PyQt6.QtGui import QBrush, QPen, QTransform, QColor, QFont, QPainterPath
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsSceneMouseEvent, QGraphicsTextItem, QGraphicsPathItem
from app.core.edge import Edge


class GraphScene(QGraphicsScene):
    MIN_VERTEX_DISTANCE = 50

    empty_space_clicked = pyqtSignal(QPointF)
    vertex_clicked = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._vertex_items = {}
        self._edge_items = {}

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.scenePos(), QTransform())

            if item is None:
                self.empty_space_clicked.emit(event.scenePos())
                event.accept()
                return

            while item is not None:
                vertex_id = item.data(0)

                if vertex_id is not None:
                    self.vertex_clicked.emit(vertex_id)
                    event.accept()
                    return

                item = item.parentItem()

        super().mousePressEvent(event)

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

    def can_place_vertex(self, pos: QPointF) -> bool:
        return all(
            QLineF(pos, circle.pos()).length() >= self.MIN_VERTEX_DISTANCE
            for circle in self._vertex_items.values()
        )

    def clear_graph(self) -> None:
        self.clear()
        self._vertex_items.clear()
        self._edge_items.clear()

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