
import json
from math import isfinite
from pathlib import Path

from app.core.graph import Graph
from app.core.exceptions import GraphError


def is_number(value) -> bool:
    return type(value) in (int, float) and isfinite(value)


def save_graph(graph: Graph, positions: dict[int, tuple[float, float]], path: str | Path) -> None:
    if set(positions) != set(graph.vertices):
        raise ValueError("Координаты вершин не соответствуют графу")

    data = {
        "version": 1,
        "vertices": [],
        "edges": []
    }

    for vertex_id in sorted(graph.vertices):
        x, y = positions[vertex_id]

        if not is_number(x) or not is_number(y):
            raise ValueError("Некорректные координаты вершины")

        data["vertices"].append({
            "id": vertex_id,
            "x": x,
            "y": y
        })

    for edge in graph.edges:
        data["edges"].append({
            "start": edge.start,
            "end": edge.end,
            "weight": edge.weight
        })

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4, allow_nan=False)


def load_graph(
    path: str | Path
) -> tuple[Graph, dict[int, tuple[float, float]]]:
    with Path(path).open("r", encoding="utf-8") as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError as error:
            raise ValueError("Некорректный формат JSON") from error

    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Неподдерживаемый формат графа")

    vertices = data.get("vertices")
    edges = data.get("edges")

    if not isinstance(vertices, list) or not isinstance(edges, list):
        raise ValueError("Отсутствуют списки вершин или рёбер")

    graph = Graph()
    positions = {}

    try:
        for vertex in vertices:
            if not isinstance(vertex, dict):
                raise ValueError("Некорректная запись вершины")

            vertex_id = vertex.get("id")
            x = vertex.get("x")
            y = vertex.get("y")

            if type(vertex_id) is not int or not is_number(x) or not is_number(y):
                raise ValueError("Некорректные данные вершины")

            if vertex_id in positions:
                raise ValueError("Повторяющийся ID вершины")

            graph.add_vertex(vertex_id)
            positions[vertex_id] = (x, y)

        for edge in edges:
            if not isinstance(edge, dict):
                raise ValueError("Некорректная запись ребра")

            start = edge.get("start")
            end = edge.get("end")
            weight = edge.get("weight")

            if type(start) is not int or type(end) is not int or not is_number(weight):
                raise ValueError("Некорректные данные ребра")

            graph.add_edge(start, end, weight)

    except GraphError as error:
        raise ValueError(f"Ошибка структуры графа: {error}") from error

    return graph, positions
