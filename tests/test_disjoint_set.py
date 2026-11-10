
from app.core.disjoint_set import DisjointSet


def test_initial_groups():
    dsu = DisjointSet([1, 2, 3])

    assert dsu.find(1) != dsu.find(2)
    assert dsu.find(2) != dsu.find(3)


def test_union():
    dsu = DisjointSet([1, 2, 3])

    assert dsu.union(1, 2) is True
    assert dsu.find(1) == dsu.find(2)
    assert dsu.find(1) != dsu.find(3)


def test_duplicate_union():
    dsu = DisjointSet([1, 2])

    assert dsu.union(1, 2) is True
    assert dsu.union(2, 1) is False


def test_merge_groups():
    dsu = DisjointSet([1, 2, 3, 4])

    dsu.union(1, 2)
    dsu.union(3, 4)
    dsu.union(2, 3)

    assert len({dsu.find(v) for v in [1, 2, 3, 4]}) == 1


def test_unknown_vertex():
    dsu = DisjointSet([1, 2])

    try:
        dsu.find(3)
    except KeyError:
        return

    raise AssertionError("Ожидалось исключение KeyError")
