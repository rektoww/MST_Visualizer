
import pytest

from app.core.graph_generator import generate_random_graph
from app.core.algorithms.kruskal import kruskal
from app.core.exceptions import GraphError


@pytest.mark.parametrize("vertices,edges", [
    (2, 1),
    (5, 4),
    (8, 12),
    (30, 435)
])
def test_generated_graph(vertices, edges):
    graph = generate_random_graph(vertices, edges, 1, 20)

    assert len(graph.vertices) == vertices
    assert len(graph.edges) == edges
    assert all(1 <= edge.weight <= 20 for edge in graph.edges)

    result = kruskal(graph)
    assert len(result.edges) == vertices - 1


def test_negative_weights():
    graph = generate_random_graph(5, 7, -10, -10)

    assert all(edge.weight == -10 for edge in graph.edges)


@pytest.mark.parametrize("vertices,edges", [
    (1, 0),
    (5, 3),
    (5, 11)
])
def test_invalid_counts(vertices, edges):
    with pytest.raises(GraphError):
        generate_random_graph(vertices, edges, 1, 20)


def test_invalid_weight_range():
    with pytest.raises(GraphError):
        generate_random_graph(5, 7, 20, 1)
