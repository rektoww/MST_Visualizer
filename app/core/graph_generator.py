
from math import isfinite
from random import choice, random, shuffle

from app.core.graph import Graph, is_number
from app.core.exceptions import GraphError


def generate_random_graph(vertex_count: int, edge_count: int, min_weight: float, max_weight: float) -> Graph:
    """Generate a connected graph, rounding weights to cents within the given interval."""
    if type(vertex_count) is not int or not 2 <= vertex_count <= 30:
        raise GraphError("Количество вершин должно быть от 2 до 30", code="generate_vertex_count")

    maximum_edges = vertex_count * (vertex_count - 1) // 2

    if type(edge_count) is not int or not vertex_count - 1 <= edge_count <= maximum_edges:
        raise GraphError("Недопустимое количество рёбер", code="generate_edge_count")

    if not is_number(min_weight) or not is_number(max_weight) or min_weight > max_weight:
        raise GraphError("Некорректный диапазон весов", code="generate_weight_range")

    lower, upper = float(min_weight), float(max_weight)
    span = upper - lower

    def sample_weight() -> float:
        fraction = random()
        weight = lower + span * fraction if isfinite(span) else lower * (1 - fraction) + upper * fraction
        return min(upper, max(lower, round(weight, 2)))

    graph = Graph()

    for vertex_id in range(1, vertex_count + 1):
        graph.add_vertex(vertex_id)

    vertices = list(range(1, vertex_count + 1))
    shuffle(vertices)

    for index in range(1, vertex_count):
        start = vertices[index]
        end = choice(vertices[:index])
        graph.add_edge(start, end, sample_weight())

    available_edges = [
        (start, end)
        for start in range(1, vertex_count + 1)
        for end in range(start + 1, vertex_count + 1)
        if not graph.has_edge(start, end)
    ]

    shuffle(available_edges)

    extra_count = edge_count - (vertex_count - 1)

    for start, end in available_edges[:extra_count]:
        graph.add_edge(start, end, sample_weight())

    return graph
