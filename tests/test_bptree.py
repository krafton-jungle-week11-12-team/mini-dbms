import random

import pytest

from mini_dbms.bptree import BPlusTree


def _build(keys, max_keys=3):
    tree = BPlusTree(max_keys=max_keys)
    for k in keys:
        tree.insert(k, k * 10)
    return tree


def _shape(node):
    """노드의 keys를 따라 트리 모양을 만들어요.

    리프는 keys 리스트, 내부 노드는 (keys, [자식 모양, ...])이에요.
    중첩 깊이가 곧 높이라서 높이도 함께 확인돼요.
    """
    if not node.children:
        return list(node.keys)
    return (list(node.keys), [_shape(child) for child in node.children])


@pytest.mark.parametrize(
    "prep, key, expected",
    [
        pytest.param(
            [1, 2, 3],
            4,
            ([3], [[1, 2], [3, 4]]),
            id="T-BPT-01 리프 분할 시 오른쪽 첫 키를 부모로 복사",
        ),
        pytest.param(
            range(1, 10),
            10,
            (
                [7],
                [
                    ([3, 5], [[1, 2], [3, 4], [5, 6]]),
                    ([9], [[7, 8], [9, 10]]),
                ],
            ),
            id="T-BPT-02 내부 노드 분할 시 가운데 키를 부모로 이동",
        ),
    ],
)
def test_split(prep, key, expected):
    tree = _build(prep)

    tree.insert(key, key * 10)

    assert _shape(tree.root) == expected


def _shuffled(n, seed=42):
    keys = list(range(1, n + 1))
    random.Random(seed).shuffle(keys)
    return keys


@pytest.mark.parametrize(
    "prep, keys, expected",
    [
        pytest.param([1, 2, 3, 4], [3], [30], id="T-BPT-03 구분 키와 같은 키"),
        pytest.param(
            range(1, 11),
            range(1, 11),
            [k * 10 for k in range(1, 11)],
            id="T-BPT-04 모든 키",
        ),
        pytest.param(range(1, 11), [0], [None], id="T-BPT-05 가장 작은 키보다 작음"),
        pytest.param(range(1, 11), [11], [None], id="T-BPT-06 가장 큰 키보다 큼"),
        pytest.param([], [1], [None], id="T-BPT-07 빈 트리"),
        pytest.param(
            _shuffled(1000),
            range(1, 1001),
            [k * 10 for k in range(1, 1001)],
            id="T-BPT-08 무작위 순서 삽입",
        ),
    ],
)
def test_search(prep, keys, expected):
    tree = _build(prep)

    assert [tree.search(k) for k in keys] == expected
