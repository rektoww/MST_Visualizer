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
            raise VertexAlreadyExistsError(f"Вершина {vertex_id} уже существует", code="graph_vertex_exists", vertex_id=vertex_id)

        self._vertices.add(vertex_id)

    def add_edge(self, start: int, end: int, weight: float) -> None:
        if start not in self._vertices:
            raise VertexNotFoundError(f"Вершина {start} не найдена", code="graph_vertex_not_found", vertex_id=start)

        if end not in self._vertices:
            raise VertexNotFoundError(f"Вершина {end} не найдена", code="graph_vertex_not_found", vertex_id=end)

        if start == end:
            raise GraphError("Петли в графе запрещены", code="graph_self_loop")

        if not isfinite(weight):
            raise GraphError("Вес должен быть конечным числом", code="graph_invalid_weight")

        first, second = sorted((start, end))
        key = (first, second)

        if key in self._edges:
            raise GraphError("Ребро уже существует", code="graph_edge_exists")

        self._edges[key] = Edge(first, second, float(weight))

    def has_edge(self, start: int, end: int) -> bool:
        first, second = sorted((start, end))
        return (first, second) in self._edges

    def remove_vertex(self, vertex_id: int) -> None:
        if vertex_id not in self._vertices:
            raise VertexNotFoundError(f"Вершина {vertex_id} не найдена", code="graph_vertex_not_found", vertex_id=vertex_id)

        self._vertices.remove(vertex_id)

        for key in tuple(self._edges):
            if vertex_id in key:
                del self._edges[key]

    def remove_edge(self, start: int, end: int) -> None:
        key = tuple(sorted((start, end)))

        if key not in self._edges:
            raise GraphError("Ребро не найдено", code="graph_edge_not_found")

        del self._edges[key]

    def set_edge_weight(self, start: int, end: int, weight: float) -> None:
        key = tuple(sorted((start, end)))

        if key not in self._edges:
            raise GraphError("Ребро не найдено", code="graph_edge_not_found")

        if not isfinite(weight):
            raise GraphError("Вес должен быть конечным числом", code="graph_invalid_weight")

        self._edges[key] = Edge(key[0], key[1], float(weight))


