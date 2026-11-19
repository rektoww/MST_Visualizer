
import json
from copy import deepcopy

import pytest

from app.core.graph import Graph
from app.core.graph_storage import graph_to_dict, edge_to_dict
from app.core.algorithms.kruskal import kruskal
from app.core.algorithms.prim import prim
from app.core.exceptions import GraphError
from app.database.calculations import decode_calculation


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


@pytest.fixture
def history_record():
    def make(algorithm, mode):
        graph = Graph()
        for vertex in range(1, 5):
            graph.add_vertex(vertex)
        for edge in [(1, 2, -2), (1, 3, -2), (2, 3, -2), (2, 4, 4), (3, 4, 8)]:
            graph.add_edge(*edge)
        result = (kruskal if algorithm == "kruskal" else prim)(graph)
        return dict(
            id=7, algorithm=algorithm, run_mode=mode, vertex_count=4, edge_count=5,
            graph_data=graph_to_dict(graph, {vertex: (100 * vertex, 100) for vertex in graph.vertices}),
            result_edges=[edge_to_dict(edge) for edge in result.edges],
            steps=[dict(edge=edge_to_dict(step.edge), accepted=step.accepted) for step in result.steps],
            total_weight=result.total_weight, duration_ms=0.25,
        )
    return make


@pytest.mark.parametrize("algorithm", ["kruskal", "prim"])
@pytest.mark.parametrize("mode", ["build", "step"])
def test_history_restores_negative_and_tied_weights(history_record, algorithm, mode):
    record = history_record(algorithm, mode)
    graph, positions, result = decode_calculation(record)
    assert graph.vertices == {1, 2, 3, 4}
    assert positions[4] == (400, 100)
    assert [step.accepted for step in result.steps] == [True, True, False, True]
    assert result.total_weight == 0


@pytest.mark.parametrize("algorithm", ["kruskal", "prim"])
def test_history_accepts_an_alternative_valid_tie_sequence(history_record, algorithm):
    record = history_record(algorithm, "step")
    record["steps"] = [
        {"edge": {"start": 1, "end": 3, "weight": -2}, "accepted": True},
        {"edge": {"start": 2, "end": 3, "weight": -2}, "accepted": True},
        {"edge": {"start": 1, "end": 2, "weight": -2}, "accepted": False},
        {"edge": {"start": 2, "end": 4, "weight": 4}, "accepted": True},
    ]
    record["result_edges"] = [step["edge"] for step in record["steps"] if step["accepted"]]
    assert decode_calculation(record)[2].edges[1].start == 2


@pytest.mark.parametrize("algorithm,mode", [("kruskal", "build"), ("prim", "step")])
@pytest.mark.parametrize("corruption", [
    "algorithm", "run_mode", "duration_ms", "vertex_count", "total_weight",
    "missing_edge", "weight", "step_type", "duplicate_step", "result_not_matching", "skips_candidate",
])
def test_history_rejects_corruption(history_record, algorithm, mode, corruption):
    record = history_record(algorithm, mode)
    if corruption in ("algorithm", "run_mode"):
        record[corruption] = "unknown"
    elif corruption in ("duration_ms", "total_weight"):
        record[corruption] += -1
    elif corruption == "vertex_count":
        record[corruption] += 1
    elif corruption == "missing_edge":
        record["steps"][0]["edge"]["end"] = 99
    elif corruption == "weight":
        record["steps"][0]["edge"]["weight"] = -3
    elif corruption == "step_type":
        record["steps"][0]["accepted"] = 1
    elif corruption == "duplicate_step":
        record["steps"].insert(1, deepcopy(record["steps"][0]))
    elif corruption == "result_not_matching":
        record["result_edges"].reverse()
    else:
        record["steps"].pop(2)

    with pytest.raises((ValueError, GraphError)):
        decode_calculation(record)


def test_prim_history_cannot_start_with_an_edge_outside_its_frontier(history_record):
    record = history_record("prim", "step")
    record["steps"][0]["edge"], record["steps"][2]["edge"] = record["steps"][2]["edge"], record["steps"][0]["edge"]
    record["result_edges"] = [step["edge"] for step in record["steps"] if step["accepted"]]
    with pytest.raises(ValueError, match="Prim candidate"):
        decode_calculation(record)
