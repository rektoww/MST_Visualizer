
import json

import pytest

from app.core.graph import Graph
from app.core.graph_storage import save_graph, load_graph
from app.core.exceptions import GraphFormatError


def test_save_and_load_graph(tmp_path):
    graph = Graph()

    for vertex_id in (1, 2, 3):
        graph.add_vertex(vertex_id)

    graph.add_edge(1, 2, 5.5)
    graph.add_edge(2, 3, -2.0)

    positions = {
        1: (100.0, 150.0),
        2: (250.0, 200.0),
        3: (400.0, 300.0)
    }

    path = tmp_path / "graphs" / "test.json"

    save_graph(graph, positions, path)

    assert path.exists()

    loaded_graph, loaded_positions = load_graph(path)

    assert loaded_graph.vertices == graph.vertices
    assert set(loaded_graph.edges) == set(graph.edges)
    assert loaded_positions == positions


def test_invalid_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(ValueError):
        load_graph(path)


def test_duplicate_vertices(tmp_path):
    path = tmp_path / "duplicate.json"

    data = {
        "version": 1,
        "vertices": [
            {"id": 1, "x": 100, "y": 100},
            {"id": 1, "x": 200, "y": 200}
        ],
        "edges": []
    }

    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError):
        load_graph(path)


def test_invalid_edge(tmp_path):
    path = tmp_path / "invalid_edge.json"

    data = {
        "version": 1,
        "vertices": [
            {"id": 1, "x": 100, "y": 100}
        ],
        "edges": [
            {"start": 1, "end": 99, "weight": 5}
        ]
    }

    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError):
        load_graph(path)


def test_invalid_positions(tmp_path):
    graph = Graph()
    graph.add_vertex(1)

    with pytest.raises(ValueError):
        save_graph(graph, {1: (float("nan"), 200)}, tmp_path / "test.json")


@pytest.mark.parametrize("version", [True, 1.0, 2])
def test_json_version_must_be_exact_integer_one(tmp_path, version):
    path = tmp_path / "test.json"
    path.write_text(json.dumps(dict(version=version, vertices=[], edges=[])), encoding="utf-8")
    with pytest.raises(GraphFormatError) as error:
        load_graph(path)
    assert error.value.code == "graph_invalid_version"


@pytest.mark.parametrize("invalid", [10**400, float("nan"), float("inf")])
def test_json_invalid_numbers_fail_as_format_errors(tmp_path, invalid):
    path = tmp_path / "test.json"
    path.write_text(json.dumps(dict(version=1, vertices=[dict(id=1, x=invalid, y=100)], edges=[])),
                    encoding="utf-8")
    with pytest.raises(GraphFormatError) as error:
        load_graph(path)
    assert error.value.code == "graph_invalid_vertex"


def test_interrupted_json_write_preserves_previous_file(tmp_path, monkeypatch):
    graph = Graph()
    graph.add_vertex(1)
    positions = {1: (100, 100)}
    path = tmp_path / "graph.json"
    save_graph(graph, positions, path)
    old_content = path.read_bytes()

    def interrupted_write(data, file, **kwargs):
        file.write('{"version":')
        raise OSError("simulated full disk")

    monkeypatch.setattr("app.core.graph_storage.json.dump", interrupted_write)
    with pytest.raises(OSError, match="full disk"):
        save_graph(graph, positions, path)
    assert path.read_bytes() == old_content
    assert list(tmp_path.iterdir()) == [path]
