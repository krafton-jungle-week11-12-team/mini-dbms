"""검증을 통과한 AST를 실행하고 Result를 반환해요."""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import List, Optional

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


class Executor:
    def __init__(self, storage, schema):
        self.storage = storage
        self.schema = schema

    def run(self, ast) -> Result:
        if isinstance(ast, InsertStmt):
            return self.run_insert(ast)
        if isinstance(ast, SelectStmt):
            return self.run_select(ast)
        raise TypeError(f"실행할 수 없는 AST: {ast!r}")

    def run_insert(self, ast: InsertStmt) -> Result:
        # 컬럼 목록 지정은 지원하지 않아서 values가 곧 스키마 순서예요.
        self.storage.append(ast.table, list(ast.values))
        return Result(columns=[], rows=[], affected=1)

    def run_select(self, ast: SelectStmt) -> Result:
        names = [name for name, _ in self.schema[ast.table]]
        index = {name: i for i, name in enumerate(names)}
        rows = [
            self._project(row, ast.columns, index)
            for _, row in self.storage.scan(ast.table)
            if self._match(row, ast.where, index)
        ]
        columns = list(ast.columns) if ast.columns is not None else names
        return Result(columns=columns, rows=rows, affected=len(rows))

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
