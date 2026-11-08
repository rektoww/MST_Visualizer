from dataclasses import dataclass

# frozen запрещяет менять поля
@dataclass(frozen=True)
class Edge:
    start: int
    end: int
    weight: int

