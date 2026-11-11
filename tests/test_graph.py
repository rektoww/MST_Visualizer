
import pytest

from app.core.edge import Edge
from app.core.graph import Graph
from app.core.exceptions import GraphError, VertexAlreadyExistsError, VertexNotFoundError


def test_empty_graph():
    graph = Graph()

    assert graph.vertices == frozenset()
    assert graph.edges == ()


def test_add_vertex():
    graph = Graph()
    graph.add_vertex(1)
    graph.add_vertex(2)

    assert graph.vertices == {1, 2}


def test_add_edge():
    graph = Graph()
    graph.add_vertex(1)
    graph.add_vertex(2)
    graph.add_edge(2, 1, 5)

    assert graph.edges == (Edge(1, 2, 5.0),)


def test_duplicate_vertex():
    graph = Graph()
    graph.add_vertex(1)

    with pytest.raises(VertexAlreadyExistsError, match="^Ошибка: Вершина 1 уже существует$"):
        graph.add_vertex(1)


def test_missing_start_vertex():
    graph = Graph()
    graph.add_vertex(2)

    with pytest.raises(VertexNotFoundError, match="^Ошибка: Вершина 1 не найдена$"):
        graph.add_edge(1, 2, 5)


def test_missing_end_vertex():
    graph = Graph()
    graph.add_vertex(1)

    with pytest.raises(VertexNotFoundError, match="^Ошибка: Вершина 2 не найдена$"):
        graph.add_edge(1, 2, 5)


def test_duplicate_edge():
    graph = Graph()
    graph.add_vertex(1)
    graph.add_vertex(2)
    graph.add_edge(1, 2, 5)

    with pytest.raises(GraphError, match="^Ошибка: Ребро уже существует$"):
        graph.add_edge(2, 1, 7)


def test_loop_edge():
    graph = Graph()
    graph.add_vertex(1)

    with pytest.raises(GraphError, match="^Ошибка: Петли в графе запрещены$"):
        graph.add_edge(1, 1, 5)


@pytest.mark.parametrize("weight", [float("inf"), float("-inf"), float("nan")])
def test_invalid_weight(weight):
    graph = Graph()
    graph.add_vertex(1)
    graph.add_vertex(2)

    with pytest.raises(GraphError, match="^Ошибка: Вес должен быть конечным числом$"):
        graph.add_edge(1, 2, weight)


@pytest.mark.parametrize("weight", [0, -5, 2.5])
def test_valid_weight(weight):
    graph = Graph()
    graph.add_vertex(1)
    graph.add_vertex(2)
    graph.add_edge(1, 2, weight)

    assert graph.edges[0].weight == weight


@pytest.mark.parametrize("error_type", [GraphError, VertexAlreadyExistsError, VertexNotFoundError])
def test_error_prefix(error_type):
    error = error_type("Тестовое сообщение")

    assert str(error) == "Ошибка: Тестовое сообщение"


def test_error_inheritance():
    assert issubclass(GraphError, ValueError)
    assert issubclass(VertexAlreadyExistsError, GraphError)
    assert issubclass(VertexNotFoundError, GraphError)

def test_has_edge():
    graph = Graph()
    graph.add_vertex(1)
    graph.add_vertex(2)

    assert graph.has_edge(1, 2) is False

    graph.add_edge(1, 2, 5)

    assert graph.has_edge(1, 2) is True
    assert graph.has_edge(2, 1) is True

def test_edit_and_remove_edges():
    graph = Graph()
    graph.add_vertex(1)
    graph.add_vertex(2)
    graph.add_vertex(3)

    graph.add_edge(1, 2, 5)
    graph.add_edge(2, 3, 7)

    graph.set_edge_weight(1, 2, -3)
    assert Edge(1, 2, -3.0) in graph.edges

    graph.remove_edge(1, 2)
    assert graph.has_edge(1, 2) is False

    graph.remove_vertex(2)
    assert 2 not in graph.vertices
    assert graph.edges == ()