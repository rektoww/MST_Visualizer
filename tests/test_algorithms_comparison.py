import pytest
from app.core.algorithms.kruskal import kruskal
from app.core.algorithms.prim import prim
from app.core.graph import Graph
from app.core.exceptions import GraphError


def test_algorithms_same_weight():
    graph = Graph()

    for vertex in range(1, 5):
        graph.add_vertex(vertex)

    graph.add_edge(1, 2, 4)
    graph.add_edge(1, 3, 2)
    graph.add_edge(2, 3, 1)
    graph.add_edge(2, 4, 7)
    graph.add_edge(3, 4, 3)

    kruskal_result = kruskal(graph)
    prim_result = prim(graph)

    assert kruskal_result.total_weight == 6
    assert prim_result.total_weight == 6
    assert len(kruskal_result.edges) == 3
    assert len(prim_result.edges) == 3


@pytest.mark.parametrize("algorithm", [kruskal, prim])
def test_mst_rejects_non_finite_total(algorithm):
    graph = Graph()
    for vertex in (1, 2, 3):
        graph.add_vertex(vertex)
    graph.add_edge(1, 2, 1e308)
    graph.add_edge(2, 3, 1e308)
    with pytest.raises(GraphError) as error:
        algorithm(graph)
    assert error.value.code == "mst_weight_overflow"
