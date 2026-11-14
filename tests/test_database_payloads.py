
import json

import pytest

from app.core.graph import Graph
from app.core.graph_storage import graph_to_dict, edge_to_dict
from app.core.algorithms.kruskal import kruskal


@pytest.fixture
def sample_graph():
    graph = Graph()

    for vertex_id in range(1, 5):
        graph.add_vertex(vertex_id)

    graph.add_edge(1, 2, 1)
    graph.add_edge(2, 3, 2)
    graph.add_edge(3, 4, 3)
    graph.add_edge(1, 3, 8)
    graph.add_edge(1, 4, 10)

    positions = {
        1: (100.0, 100.0),
        2: (200.0, 100.0),
        3: (200.0, 200.0),
        4: (100.0, 200.0)
    }

    return graph, positions


def test_graph_to_dict_structure(sample_graph):
    graph, positions = sample_graph
    data = graph_to_dict(graph, positions)

    assert data["version"] == 1
    assert len(data["vertices"]) == 4
    assert len(data["edges"]) == 5


def test_graph_to_dict_positions(sample_graph):
    graph, positions = sample_graph
    data = graph_to_dict(graph, positions)

    saved_positions = {
        vertex["id"]: (vertex["x"], vertex["y"])
        for vertex in data["vertices"]
    }

    assert saved_positions == positions


def test_graph_to_dict_edges(sample_graph):
    graph, positions = sample_graph
    data = graph_to_dict(graph, positions)

    saved_edges = {
        (edge["start"], edge["end"], edge["weight"])
        for edge in data["edges"]
    }

    original_edges = {
        (edge.start, edge.end, edge.weight)
        for edge in graph.edges
    }

    assert saved_edges == original_edges


def test_graph_data_json_serializable(sample_graph):
    graph, positions = sample_graph
    data = graph_to_dict(graph, positions)

    restored = json.loads(json.dumps(data))

    assert restored == data


def test_mst_result_serialization(sample_graph):
    graph, _ = sample_graph
    result = kruskal(graph)

    result_edges = [edge_to_dict(edge) for edge in result.edges]
    steps = [
        {"edge": edge_to_dict(step.edge), "accepted": step.accepted}
        for step in result.steps
    ]

    payload = {
        "result_edges": result_edges,
        "steps": steps,
        "total_weight": result.total_weight
    }

    restored = json.loads(json.dumps(payload))

    assert restored["total_weight"] == pytest.approx(6.0)
    assert len(restored["result_edges"]) == 3
    assert len([step for step in restored["steps"] if step["accepted"]]) == 3
