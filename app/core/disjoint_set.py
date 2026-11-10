from collections.abc import Iterable


class DisjointSet:
    def __init__(self, vertices: Iterable[int]) -> None:
        self._parent = {vertex: vertex for vertex in vertices}
        self._size = {vertex: 1 for vertex in self._parent}

    def find(self, vertex: int) -> int:
        if self._parent[vertex] != vertex:
            self._parent[vertex] = self.find(self._parent[vertex]) # сжатие путей

        return self._parent[vertex]

    def union(self, first: int, second: int) -> bool:
        root_first = self.find(first)
        root_second = self.find(second)

        if root_first == root_second:
            return False

        if self._size[root_first] < self._size[root_second]:
            root_first, root_second = root_second, root_first

        self._parent[root_second] = root_first
        self._size[root_first] += self._size[root_second]

        return True
