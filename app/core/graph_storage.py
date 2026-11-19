import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.core.graph import Graph, is_number
from app.core.exceptions import GraphError, GraphFormatError
from app.core.edge import Edge


def edge_to_dict(edge: Edge) -> dict:
    return {"start": edge.start, "end": edge.end, "weight": edge.weight}

def save_graph(graph: Graph, positions: dict[int, tuple[float, float]], path: str | Path) -> None:
    data = graph_to_dict(graph, positions)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as file:
            temporary_path = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=4, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

def graph_to_dict(graph: Graph, positions: dict[int, tuple[float, float]]) -> dict:
    if set(positions) != set(graph.vertices):
        raise GraphFormatError("Координаты вершин не соответствуют графу", code="graph_invalid_positions")

    data = {"version": 1, "vertices": [], "edges": []}

    for vertex_id in sorted(graph.vertices):
        x, y = positions[vertex_id]

        if not is_number(x) or not is_number(y):
            raise GraphFormatError("Некорректные координаты вершины", code="invalid_coords")

        data["vertices"].append({"id": vertex_id, "x": x, "y": y})

    for edge in graph.edges:
        data["edges"].append(edge_to_dict(edge))

    return data

def load_graph(
    path: str | Path
) -> tuple[Graph, dict[int, tuple[float, float]]]:
    with Path(path).open("r", encoding="utf-8") as file:
        try:
            data = json.load(file)
        except (ValueError, RecursionError) as error:
            raise GraphFormatError("Некорректный формат JSON", code="graph_invalid_json") from error

    return graph_from_dict(data)


def graph_from_dict(data: dict) -> tuple[Graph, dict[int, tuple[float, float]]]:
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise GraphFormatError("Неподдерживаемый формат графа", code="graph_invalid_version")

    vertices = data.get("vertices")
    edges = data.get("edges")

    if not isinstance(vertices, list) or not isinstance(edges, list):
        raise GraphFormatError("Отсутствуют списки вершин или рёбер", code="graph_invalid_records")

    graph = Graph()
    positions = {}

    for vertex in vertices:
        if not isinstance(vertex, dict):
            raise GraphFormatError("Некорректная запись вершины", code="graph_invalid_vertex")

        vertex_id = vertex.get("id")
        x = vertex.get("x")
        y = vertex.get("y")

        if type(vertex_id) is not int or not is_number(x) or not is_number(y):
            raise GraphFormatError("Некорректные данные вершины", code="graph_invalid_vertex")

        if vertex_id in positions:
            raise GraphFormatError("Повторяющийся ID вершины", code="graph_vertex_exists", vertex_id=vertex_id)

        graph.add_vertex(vertex_id)
        positions[vertex_id] = (float(x), float(y))

    try:
        for edge in edges:
            parsed = edge_from_dict(edge)
            graph.add_edge(parsed.start, parsed.end, parsed.weight)
    except GraphFormatError:
        raise
    except GraphError as error:
        raise GraphFormatError(str(error), code=error.code, **error.params) from error

    return graph, positions


def edge_from_dict(data: dict) -> Edge:
    if not isinstance(data, dict):
        raise GraphFormatError("Некорректная запись ребра", code="graph_invalid_edge")

    start, end, weight = data.get("start"), data.get("end"), data.get("weight")
    if type(start) is not int or type(end) is not int or not is_number(weight):
        raise GraphFormatError("Некорректные данные ребра", code="graph_invalid_edge")

    first, second = sorted((start, end))
    return Edge(first, second, float(weight))
