"""id → offset을 저장하는 B+ 트리 인덱스예요."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from typing import Any, List, Optional


class Node:
    """리프는 keys와 values를, 내부 노드는 keys와 children을 가져요."""

    def __init__(self, leaf: bool):
        self.keys: List[Any] = []
        self.children: List[Node] = []  # 내부 노드만 사용
        self.values: List[Any] = []  # 리프만 사용
        self.leaf = leaf


class BPlusTree:
    def __init__(self, max_keys: int = 64):
        if max_keys < 3:
            raise ValueError("max_keys는 3 이상이어야 해요")
        self.max_keys = max_keys
        self.root = Node(leaf=True)

    def search(self, key) -> Optional[Any]:
        node = self._find_leaf(key)
        i = bisect_left(node.keys, key)
        if i < len(node.keys) and node.keys[i] == key:
            return node.values[i]
        return None

    def insert(self, key, value) -> None:
        # 루트에서 리프까지 지나온 내부 노드를 기억해 두고, 분할을 위로 올려요.
        path = []
        node = self.root
        while not node.leaf:
            path.append(node)
            node = node.children[bisect_right(node.keys, key)]

        i = bisect_left(node.keys, key)
        if i < len(node.keys) and node.keys[i] == key:
            node.values[i] = value  # 같은 키면 값만 바꿔요
            return
        node.keys.insert(i, key)
        node.values.insert(i, value)

        split = self._split_leaf(node) if len(node.keys) > self.max_keys else None
        while split is not None:
            up_key, right = split
            if not path:
                new_root = Node(leaf=False)
                new_root.keys = [up_key]
                new_root.children = [self.root, right]
                self.root = new_root
                return
            parent = path.pop()
            j = bisect_right(parent.keys, up_key)
            parent.keys.insert(j, up_key)
            parent.children.insert(j + 1, right)
            split = self._split_internal(parent) if len(parent.keys) > self.max_keys else None

    def _find_leaf(self, key) -> Node:
        node = self.root
        while not node.leaf:
            node = node.children[bisect_right(node.keys, key)]
        return node

    @staticmethod
    def _split_leaf(node: Node):
        """반으로 나누고, 오른쪽 첫 키를 부모로 복사해요."""
        mid = len(node.keys) // 2
        right = Node(leaf=True)
        right.keys, node.keys = node.keys[mid:], node.keys[:mid]
        right.values, node.values = node.values[mid:], node.values[:mid]
        return right.keys[0], right

    @staticmethod
    def _split_internal(node: Node):
        """가운데 키를 부모로 이동해요. 가운데가 둘이면 오른쪽 키를 써요."""
        mid = len(node.keys) // 2
        up_key = node.keys[mid]
        right = Node(leaf=False)
        right.keys, node.keys = node.keys[mid + 1:], node.keys[:mid]
        right.children, node.children = node.children[mid + 1:], node.children[:mid + 1]
        return up_key, right
