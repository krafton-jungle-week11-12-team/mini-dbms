"""파서가 만드는 AST 노드."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Union

Value = Union[int, str]


@dataclass
class Condition:
    column: str
    op: str  # = != < > <= >=
    value: Value


@dataclass
class InsertStmt:
    table: str
    values: List[Value]


@dataclass
class SelectStmt:
    table: str
    columns: Optional[List[str]]  # SELECT * 이면 None
    where: Optional[Condition]
