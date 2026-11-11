from math import isfinite

from app.core.edge import Edge

from app.core.exceptions import GraphError, VertexAlreadyExistsError, VertexNotFoundError

class Graph:
    def __init__(self) -> None:
        self._vertices: set[int] = set()
        self._edges: dict[tuple[int, int], Edge] = {}

    # Декоратор property чтобы можно было обращаться к методу как к обычному атрибуту, типо graph.vertices
    @property
    def vertices(self) -> frozenset[int]:
        return frozenset(self._vertices)

    @property
    def edges(self) -> tuple[Edge, ...]:
        return tuple(self._edges.values())

    def add_vertex(self, vertex_id: int) -> None:
        if vertex_id in self._vertices:
            raise VertexAlreadyExistsError(f"Вершина {vertex_id} уже существует")

        self._vertices.add(vertex_id)

    def add_edge(self, start: int, end: int, weight: float) -> None:
        if start not in self._vertices:
            raise VertexNotFoundError(f"Вершина {start} не найдена")

        if end not in self._vertices:
            raise VertexNotFoundError(f"Вершина {end} не найдена")

        if start == end:
            raise GraphError("Петли в графе запрещены")

        if not isfinite(weight):
            raise GraphError("Вес должен быть конечным числом")

        first, second = sorted((start, end))
        key = (first, second)

        if key in self._edges:
            raise GraphError("Ребро уже существует")

        self._edges[key] = Edge(first, second, float(weight))

    def has_edge(self, start: int, end: int) -> bool:
        first, second = sorted((start, end))
        return (first, second) in self._edges

    def remove_vertex(self, vertex_id: int) -> None:
        if vertex_id not in self._vertices:
            raise VertexNotFoundError(f"Вершина {vertex_id} не найдена")

        self._vertices.remove(vertex_id)

        for key in tuple(self._edges):
            if vertex_id in key:
                del self._edges[key]

    def remove_edge(self, start: int, end: int) -> None:
        key = tuple(sorted((start, end)))

        if key not in self._edges:
            raise GraphError("Ребро не найдено")

        del self._edges[key]

    def set_edge_weight(self, start: int, end: int, weight: float) -> None:
        key = tuple(sorted((start, end)))

        if key not in self._edges:
            raise GraphError("Ребро не найдено")

        if not isfinite(weight):
            raise GraphError("Вес должен быть конечным числом")

        self._edges[key] = Edge(key[0], key[1], float(weight))


