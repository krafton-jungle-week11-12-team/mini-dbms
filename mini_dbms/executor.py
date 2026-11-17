"""검증을 통과한 AST를 실행하고 Result를 반환해요."""

from __future__ import annotations

import operator
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
    used_index: bool = False  # SELECT가 B+ 트리 인덱스로 읽었는지


# 인덱스 컬럼을 따로 주지 않으면 모든 테이블이 id를 인덱스로 써요.
DEFAULT_INDEX_KEY = "id"


class Executor:
    def __init__(self, storage, schema, index_keys=None):
        self.storage = storage
        self.schema = schema
        self.index_keys = index_keys or {}
        self.indexes = {}  # 테이블 → BPlusTree
        self.next_id = {}  # 테이블 → 다음에 줄 id
        for table in schema:
            self._load(table)

    def _key_column(self, table: str) -> str:
        return self.index_keys.get(table, DEFAULT_INDEX_KEY)

    def _key_pos(self, table: str) -> int:
        names = [name for name, _ in self.schema[table]]
        return names.index(self._key_column(table))

    def _load(self, table: str) -> None:
        """파일을 한 번 훑어 인덱스 트리와 next_id를 복구해요."""
        tree = BPlusTree()
        pos = self._key_pos(table)
        max_id = 0
        for offset, record in self.storage.scan(table):
            tree.insert(record[pos], offset)
            max_id = max(max_id, record[pos])
        self.indexes[table] = tree
        self.next_id[table] = max_id + 1

    def run(self, ast) -> Result:
        if isinstance(ast, InsertStmt):
            return self.run_insert(ast)
        if isinstance(ast, SelectStmt):
            return self.run_select(ast)
        raise TypeError(f"실행할 수 없는 AST: {ast!r}")

    def run_insert(self, ast: InsertStmt) -> Result:
        # 컬럼 목록 지정은 지원하지 않아서 values는 id를 뺀 스키마 순서예요.
        new_id = self.next_id[ast.table]
        record = list(ast.values)
        record.insert(self._key_pos(ast.table), new_id)
        offset = self.storage.append(ast.table, record)
        self.indexes[ast.table].insert(new_id, offset)
        self.next_id[ast.table] = new_id + 1
        return Result(columns=[], rows=[], affected=1, type="insert", inserted_id=new_id)

    def run_select(self, ast: SelectStmt) -> Result:
        names = [name for name, _ in self.schema[ast.table]]
        index = {name: i for i, name in enumerate(names)}
        used_index = self._is_id_lookup(ast.table, ast.where)
        if used_index:  # WHERE id = ?
            offset = self.indexes[ast.table].search(ast.where.value)
            records = [] if offset is None else [self.storage.read_at(ast.table, offset)]
        else:  # 그 외 → 선형 탐색
            records = (row for _, row in self.storage.scan(ast.table))
        rows = [
            self._project(row, ast.columns, index)
            for row in records
            if self._match(row, ast.where, index)
        ]
        columns = list(ast.columns) if ast.columns is not None else names
        return Result(
            columns=columns, rows=rows, affected=len(rows),
            type="select", used_index=used_index,
        )

    def _is_id_lookup(self, table: str, condition: Optional[Condition]) -> bool:
        return (
            condition is not None
            and condition.column == self._key_column(table)
            and condition.op == "="
        )

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
