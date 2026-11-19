import logging
from heapq import heappop, heappush
from math import isclose

import psycopg
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row

from app.database.connection import get_connection
from app.core.algorithms.result import AlgorithmStep, MSTResult
from app.core.disjoint_set import DisjointSet
from app.core.edge import Edge
from app.core.exceptions import GraphError
from app.core.graph import Graph, is_number
from app.core.graph_storage import edge_from_dict, graph_from_dict


logger = logging.getLogger(__name__)


def decode_calculation(data: dict) -> tuple[Graph, dict[int, tuple[float, float]], MSTResult]:
    if not isinstance(data, dict) or data.get("algorithm") not in ("kruskal", "prim"):
        raise ValueError("Invalid calculation algorithm")
    if data.get("run_mode") not in ("build", "step"):
        raise ValueError("Invalid calculation mode")
    if type(data.get("id")) is not int or data["id"] <= 0:
        raise ValueError("Invalid calculation ID")
    if not is_number(data.get("duration_ms")) or data["duration_ms"] < 0:
        raise ValueError("Invalid calculation duration")
    if not is_number(data.get("total_weight")):
        raise ValueError("Invalid total weight")

    graph, positions = graph_from_dict(data.get("graph_data"))
    vertices, edges = graph.vertices, graph.edges
    if (not vertices or type(data.get("vertex_count")) is not int or data["vertex_count"] != len(vertices)
            or type(data.get("edge_count")) is not int or data["edge_count"] != len(edges)):
        raise GraphError("Количество вершин или рёбер не соответствует сохранённому расчёту",
                         code="history_graph_mismatch")

    if not isinstance(data.get("result_edges"), list) or not isinstance(data.get("steps"), list):
        raise ValueError("Invalid edges or steps")

    graph_edges = {(edge.start, edge.end): edge for edge in edges}

    def restore_edge(raw: dict) -> Edge:
        edge = edge_from_dict(raw)
        if graph_edges.get((edge.start, edge.end)) != edge:
            raise ValueError("Calculation edge does not match the graph")
        return edge

    result_edges = tuple(restore_edge(raw) for raw in data["result_edges"])
    steps = []
    for raw in data["steps"]:
        if not isinstance(raw, dict) or type(raw.get("accepted")) is not bool:
            raise ValueError("Invalid step decision")
        steps.append(AlgorithmStep(restore_edge(raw.get("edge")), raw["accepted"]))

    accepted = tuple(step.edge for step in steps if step.accepted)
    if (accepted != result_edges or len(accepted) != len(vertices) - 1
            or len({step.edge for step in steps}) != len(steps)
            or (steps and not steps[-1].accepted)):
        raise ValueError("Steps do not match the spanning tree")

    if data["algorithm"] == "kruskal":
        # Equal-weight edges may appear in any order, but weights cannot be skipped.
        weights = sorted(edge.weight for edge in edges)
        sets = DisjointSet(vertices)
        for weight, step in zip(weights, steps):
            if step.edge.weight != weight or sets.union(step.edge.start, step.edge.end) != step.accepted:
                raise ValueError("Invalid Kruskal step")
    else:
        validate_prim_steps(vertices, edges, steps)

    total = 0.0
    for edge in accepted:
        total += edge.weight
    if not isclose(total, data["total_weight"], rel_tol=1e-12):
        raise ValueError("Total weight does not match the spanning tree")

    return graph, positions, MSTResult(result_edges, float(data["total_weight"]), tuple(steps))


def validate_prim_steps(vertices: frozenset[int], edges: tuple[Edge, ...], steps: list[AlgorithmStep]) -> None:
    adjacency = {vertex: [] for vertex in vertices}
    for edge in edges:
        adjacency[edge.start].append(edge)
        adjacency[edge.end].append(edge)

    visited = set()
    pending = set()
    candidates = []

    def visit(vertex: int) -> None:
        visited.add(vertex)
        for edge in adjacency[vertex]:
            other = edge.end if edge.start == vertex else edge.start
            if other not in visited:
                key = (edge.weight, edge.start, edge.end)
                heappush(candidates, key)
                pending.add(key)

    visit(min(vertices))
    for step in steps:
        edge = step.edge
        key = (edge.weight, edge.start, edge.end)
        while candidates and candidates[0] not in pending:
            heappop(candidates)
        # Any pending edge with the minimum weight is a valid tie choice.
        if key not in pending or candidates[0][0] != edge.weight:
            raise ValueError("Invalid Prim candidate")
        pending.remove(key)
        accepted = edge.start not in visited or edge.end not in visited
        if accepted != step.accepted:
            raise ValueError("Invalid Prim decision")
        if accepted:
            visit(edge.end if edge.start in visited else edge.start)


def add_calculation(algorithm: str, run_mode: str, vertex_count: int, edge_count: int,
                    graph_data: dict, result_edges: list, steps: list,
                    total_weight: float, duration_ms: float) -> int | None:
    try:
        with get_connection() as connection:
            result = connection.execute(
                """INSERT INTO calculations
                   (algorithm, run_mode, vertex_count, edge_count, graph_data,
                    result_edges, steps, total_weight, duration_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (algorithm, run_mode, vertex_count, edge_count, Jsonb(graph_data),
                 Jsonb(result_edges), Jsonb(steps), total_weight, duration_ms)
            )
            calculation_id = result.fetchone()[0]

        logger.info("Calculation saved: id=%s, algorithm=%s, mode=%s", calculation_id, algorithm, run_mode)
        return calculation_id

    except psycopg.Error:
        logger.exception("Failed to save calculation: algorithm=%s", algorithm)
        return None

def get_calculations(limit: int = 100) -> list[dict] | None:
    limit = max(1, min(limit, 500))

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT id, created_at, algorithm, run_mode, vertex_count,
                              edge_count, total_weight, duration_ms
                       FROM calculations
                       ORDER BY created_at DESC, id DESC
                       LIMIT %s""",
                    (limit,)
                )
                return cursor.fetchall()

    except psycopg.Error:
        logger.exception("Failed to load calculations")
        return None


def get_calculation_by_id(calculation_id: int) -> dict | None:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT * FROM calculations WHERE id = %s", (calculation_id,))
                return cursor.fetchone()

    except psycopg.Error:
        logger.exception("Failed to load calculation: id=%s", calculation_id)
        raise
