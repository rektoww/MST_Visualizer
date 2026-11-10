
import pytest

from app.core.algorithms.kruskal import kruskal
from app.core.edge import Edge
from app.core.exceptions import GraphError
from app.core.graph import Graph


def test_kruskal_builds_mst():
    graph = Graph()

    for vertex in range(1, 5):
        graph.add_vertex(vertex)

    graph.add_edge(1, 2, 1)
    graph.add_edge(2, 3, 2)
    graph.add_edge(1, 3, 3)
    graph.add_edge(3, 4, 4)

    result = kruskal(graph)

    assert result.total_weight == 7
    assert result.edges == (Edge(1, 2, 1.0), Edge(2, 3, 2.0), Edge(3, 4, 4.0))
    assert [step.accepted for step in result.steps] == [True, True, False, True]


def test_kruskal_disconnected_graph():
    graph = Graph()

    for vertex in range(1, 4):
        graph.add_vertex(vertex)

    graph.add_edge(1, 2, 5)

    with pytest.raises(GraphError, match="граф несвязный"):
        kruskal(graph)


def test_kruskal_single_vertex():
    graph = Graph()
    graph.add_vertex(1)

    result = kruskal(graph)

    assert result.total_weight == 0
    assert result.edges == ()
    assert result.steps == ()


def test_kruskal_empty_graph():
    graph = Graph()

    with pytest.raises(GraphError, match="Граф не содержит вершин"):
        kruskal(graph)


def test_kruskal_negative_weight():
    graph = Graph()

    for vertex in range(1, 4):
        graph.add_vertex(vertex)

    graph.add_edge(1, 2, -5)
    graph.add_edge(2, 3, 2)
    graph.add_edge(1, 3, 10)

    result = kruskal(graph)

    assert result.total_weight == -3
    assert len(result.edges) == 2
