from dataclasses import dataclass

from app.core.edge import Edge

@dataclass(frozen=True)
class AlgorithmStep:
    edge: Edge
    accepted: bool

@dataclass(frozen=True)
class MSTResult:
    edges: tuple[Edge, ...]
    total_weight: float
    steps: tuple[AlgorithmStep, ...]

