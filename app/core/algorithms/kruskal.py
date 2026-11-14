from app.core.disjoint_set import DisjointSet
from app.core.exceptions import GraphError
from app.core.graph import Graph
from app.core.algorithms.result import AlgorithmStep, MSTResult

def kruskal(graph: Graph) -> MSTResult:
    if not graph.vertices:
        raise GraphError("Граф не содержит вершин", code="graph_empty")

    dsu = DisjointSet(graph.vertices)

    selected_edges = []
    steps = []
    total_weight = 0.0

    sorted_edges = sorted(graph.edges, key=lambda edge: (edge.weight, edge.start, edge.end))

    for edge in sorted_edges:
        accepted = dsu.union(edge.start, edge.end)
        steps.append(AlgorithmStep(edge, accepted))

        if accepted:
            selected_edges.append(edge)
            total_weight += edge.weight

            if len(selected_edges) == len(graph.vertices) - 1:
                break

    if len(selected_edges) != len(graph.vertices) - 1:
        raise GraphError("Невозможно построить остов: граф несвязный", code="graph_disconnected")

    return MSTResult(tuple(selected_edges), total_weight, tuple(steps))