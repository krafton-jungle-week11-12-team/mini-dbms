"""검증을 통과한 AST를 실행하고 Result를 반환해요."""

from __future__ import annotations

import operator
import threading
from dataclasses import dataclass, field
from typing import List, Optional

from mini_dbms.bptree import BPlusTree
from mini_dbms.nodes import Condition, InsertStmt, SelectStmt

_OPS = {
    "=": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}


@dataclass
class Result:
    columns: List[str] = field(default_factory=list)
    rows: List[list] = field(default_factory=list)
    affected: int = 0
    type: str = ""  # "insert" / "select"
    inserted_id: Optional[int] = None  # INSERT로 부여한 id
    used_index: bool = False  # SELECT가 B+ 트리 인덱스(기본 키 또는 보조)로 읽었는지
    index_column: Optional[str] = None  # 사용한 인덱스의 컬럼 이름. 선형 탐색이면 None


# 인덱스 컬럼을 따로 주지 않으면 모든 테이블이 id를 인덱스로 써요.
DEFAULT_INDEX_KEY = "id"


def _index_add(tree: BPlusTree, key, offset: int) -> None:
    """중복 키를 허용하는 보조 인덱스에 offset을 추가해요.

    BPlusTree.insert()는 같은 키면 값을 덮어쓰므로, 값을 offset 리스트로 두고
    키가 이미 있으면 그 리스트에 이어 붙여요. offset은 늘어나는 순서로 들어와서
    리스트는 항상 삽입 순서예요.
    """
    offsets = tree.search(key)
    if offsets is None:
        tree.insert(key, [offset])
    else:
        offsets.append(offset)


class Executor:
    def __init__(self, storage, schema, index_keys=None, secondary_indexes=None):
        self.storage = storage
        self.schema = schema
        self.index_keys = index_keys or {}
        self.indexes = {}  # 테이블 → BPlusTree
        # 테이블 → {컬럼: BPlusTree}. 값은 offset 리스트예요.
        self.secondary = {
            table: {column: None for column in columns}
            for table, columns in (secondary_indexes or {}).items()
        }
        self.next_id = {}  # 테이블 → 다음에 줄 id
        # 테이블마다 락 하나. 같은 테이블의 INSERT와 SELECT가 같은 락을 써요.
        self.locks = {table: threading.Lock() for table in schema}
        for table in schema:
            self._load(table)

    def _key_column(self, table: str) -> str:
        return self.index_keys.get(table, DEFAULT_INDEX_KEY)

    def _key_pos(self, table: str) -> int:
        names = [name for name, _ in self.schema[table]]
        return names.index(self._key_column(table))

    def _secondary_positions(self, table: str) -> list:
        """(컬럼 위치, 보조 트리) 목록이에요."""
        names = [name for name, _ in self.schema[table]]
        return [
            (names.index(column), tree)
            for column, tree in self.secondary.get(table, {}).items()
        ]

    def _load(self, table: str) -> None:
        """파일을 한 번 훑어 인덱스 트리(기본 키, 보조)와 next_id를 복구해요."""
        tree = BPlusTree()
        for column in self.secondary.get(table, {}):
            self.secondary[table][column] = BPlusTree()
        secondary = self._secondary_positions(table)
        pos = self._key_pos(table)
        max_id = 0
        for offset, record in self.storage.scan(table):
            tree.insert(record[pos], offset)
            for col_pos, sec_tree in secondary:
                _index_add(sec_tree, record[col_pos], offset)
            max_id = max(max_id, record[pos])
        self.indexes[table] = tree
        self.next_id[table] = max_id + 1

    def run(self, ast) -> Result:
        # run_insert()와 run_select() 안에서는 다시 잡지 않아요. Lock은 재진입이 안 돼요.
        if isinstance(ast, (InsertStmt, SelectStmt)):
            with self.locks[ast.table]:
                if isinstance(ast, InsertStmt):
                    return self.run_insert(ast)
                return self.run_select(ast)
        raise TypeError(f"실행할 수 없는 AST: {ast!r}")

    def run_insert(self, ast: InsertStmt) -> Result:
        # 컬럼 목록 지정은 지원하지 않아서 values는 id를 뺀 스키마 순서예요.
        new_id = self.next_id[ast.table]
        record = list(ast.values)
        record.insert(self._key_pos(ast.table), new_id)
        offset = self.storage.append(ast.table, record)
        self.indexes[ast.table].insert(new_id, offset)
        for col_pos, sec_tree in self._secondary_positions(ast.table):
            _index_add(sec_tree, record[col_pos], offset)
        self.next_id[ast.table] = new_id + 1
        return Result(columns=[], rows=[], affected=1, type="insert", inserted_id=new_id)

    def run_select(self, ast: SelectStmt) -> Result:
        names = [name for name, _ in self.schema[ast.table]]
        index = {name: i for i, name in enumerate(names)}
        sec_tree = self._secondary_lookup(ast.table, ast.where)
        index_column = None
        if self._is_id_lookup(ast.table, ast.where):  # WHERE id = ?
            used_index = True
            index_column = ast.where.column
            offset = self.indexes[ast.table].search(ast.where.value)
            records = [] if offset is None else [self.storage.read_at(ast.table, offset)]
        elif sec_tree is not None:  # WHERE <보조 인덱스 컬럼> = ?
            used_index = True
            index_column = ast.where.column
            offsets = sec_tree.search(ast.where.value) or []
            records = [self.storage.read_at(ast.table, off) for off in offsets]
        else:  # 그 외 → 선형 탐색
            used_index = False
            records = (row for _, row in self.storage.scan(ast.table))
        rows = [
            self._project(row, ast.columns, index)
            for row in records
            if self._match(row, ast.where, index)
        ]
        columns = list(ast.columns) if ast.columns is not None else names
        return Result(
            columns=columns, rows=rows, affected=len(rows),
            type="select", used_index=used_index, index_column=index_column,
        )

    def _is_id_lookup(self, table: str, condition: Optional[Condition]) -> bool:
        return (
            condition is not None
            and condition.column == self._key_column(table)
            and condition.op == "="
        )

    def _secondary_lookup(self, table: str, condition: Optional[Condition]):
        """조건이 보조 인덱스 컬럼의 = 이면 그 트리를, 아니면 None을 돌려줘요."""
        if condition is None or condition.op != "=":
            return None
        return self.secondary.get(table, {}).get(condition.column)

    @staticmethod
    def _match(row: list, condition: Optional[Condition], index: dict) -> bool:
        if condition is None:
            return True
        return _OPS[condition.op](row[index[condition.column]], condition.value)

    @staticmethod
    def _project(row: list, columns: Optional[List[str]], index: dict) -> list:
        if columns is None:
            return list(row)
        return [row[index[name]] for name in columns]
