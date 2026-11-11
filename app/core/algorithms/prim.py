from heapq import heappop, heappush

from app.core.algorithms.result import AlgorithmStep, MSTResult
from app.core.exceptions import GraphError
from app.core.graph import Graph

def prim(graph: Graph) -> MSTResult:
    if not graph.vertices:
        raise GraphError("Граф не содержит вершин")

    adjacency = {vertex: [] for vertex in graph.vertices}

    for edge in graph.edges:
        adjacency[edge.start].append(edge)
        adjacency[edge.end].append(edge)

    start = min(graph.vertices)
    visited = {start}

    candidates = []
    selected_edges = []
    steps = []
    total_weight = 0.0

    for edge in adjacency[start]:
        heappush(candidates, (edge.weight, edge.start, edge.end, edge))

    while candidates and len(visited) < len(graph.vertices):
        _, _, _, edge = heappop(candidates)

        if edge.start in visited and edge.end in visited:
            steps.append(AlgorithmStep(edge, False))
            continue

        steps.append(AlgorithmStep(edge, True))
        selected_edges.append(edge)
        total_weight += edge.weight

        new_vertex = edge.start if edge.start not in visited else edge.end
        visited.add(new_vertex)

        for next_edge in adjacency[new_vertex]:
            other = next_edge.end if next_edge.start == new_vertex else next_edge.start

            if other not in visited:
                heappush(candidates, (next_edge.weight, next_edge.start, next_edge.end, next_edge))

    if len(visited) != len(graph.vertices):
        raise GraphError("Невозможно построить остов: граф несвязный")

    return MSTResult(tuple(selected_edges), total_weight, tuple(steps))