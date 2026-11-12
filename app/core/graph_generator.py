
from math import isfinite
from random import choice, shuffle, uniform

from app.core.graph import Graph
from app.core.exceptions import GraphError


def generate_random_graph(vertex_count: int, edge_count: int, min_weight: float, max_weight: float) -> Graph:
    if not 2 <= vertex_count <= 30:
        raise GraphError("Количество вершин должно быть от 2 до 30")

    maximum_edges = vertex_count * (vertex_count - 1) // 2

    if not vertex_count - 1 <= edge_count <= maximum_edges:
        raise GraphError("Недопустимое количество рёбер")

    if not isfinite(min_weight) or not isfinite(max_weight) or min_weight > max_weight:
        raise GraphError("Некорректный диапазон весов")

    graph = Graph()

    for vertex_id in range(1, vertex_count + 1):
        graph.add_vertex(vertex_id)

    vertices = list(range(1, vertex_count + 1))
    shuffle(vertices)

    for index in range(1, vertex_count):
        start = vertices[index]
        end = choice(vertices[:index])
        weight = round(uniform(min_weight, max_weight), 2)
        graph.add_edge(start, end, weight)

    available_edges = [
        (start, end)
        for start in range(1, vertex_count + 1)
        for end in range(start + 1, vertex_count + 1)
        if not graph.has_edge(start, end)
    ]

    shuffle(available_edges)

    extra_count = edge_count - (vertex_count - 1)

    for start, end in available_edges[:extra_count]:
        weight = round(uniform(min_weight, max_weight), 2)
        graph.add_edge(start, end, weight)

    return graph
