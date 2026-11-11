
import pytest

from app.core.algorithms.prim import prim
from app.core.edge import Edge
from app.core.exceptions import GraphError
from app.core.graph import Graph


def test_prim_builds_mst():
    graph = Graph()

    for vertex in range(1, 5):
        graph.add_vertex(vertex)

    graph.add_edge(1, 2, 2)
    graph.add_edge(2, 4, 5)
    graph.add_edge(1, 3, 6)
    graph.add_edge(3, 4, 7)

    result = prim(graph)

    assert result.total_weight == 13
    assert result.edges == (Edge(1, 2, 2.0), Edge(2, 4, 5.0), Edge(1, 3, 6.0))
    assert len(result.steps) == 3


def test_prim_disconnected_graph():
    graph = Graph()

    for vertex in range(1, 4):
        graph.add_vertex(vertex)

    graph.add_edge(1, 2, 5)

    with pytest.raises(GraphError, match="граф несвязный"):
        prim(graph)


def test_prim_single_vertex():
    graph = Graph()
    graph.add_vertex(1)

    result = prim(graph)

    assert result.total_weight == 0
    assert result.edges == ()
    assert result.steps == ()


def test_prim_empty_graph():
    graph = Graph()

    with pytest.raises(GraphError, match="Граф не содержит вершин"):
        prim(graph)
