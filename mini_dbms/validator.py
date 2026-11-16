"""AST를 스키마와 비교해요. 통과한 AST만 실행기로 넘어가요."""

from __future__ import annotations

from mini_dbms.errors import ValidationError
from mini_dbms.nodes import InsertStmt, SelectStmt

__all__ = ["ValidationError", "validate"]

_PY_TYPE = {"INT": int, "TEXT": str}


def _type_ok(value, col_type: str) -> bool:
    # bool은 int의 하위 타입이지만 값으로 나올 일이 없어요.
    return isinstance(value, _PY_TYPE[col_type])


def validate(ast, schema) -> None:
    if ast.table not in schema:
        raise ValidationError(f"없는 테이블 '{ast.table}'")
    columns = schema[ast.table]
    types = dict(columns)

    if isinstance(ast, InsertStmt):
        if len(ast.values) != len(columns):
            raise ValidationError("값 개수가 컬럼 수와 다름")
        for (name, col_type), value in zip(columns, ast.values):
            if not _type_ok(value, col_type):
                raise ValidationError(f"컬럼 '{name}'의 타입과 맞지 않음")
        return

    if isinstance(ast, SelectStmt):
        for name in ast.columns or []:
            if name not in types:
                raise ValidationError(f"없는 컬럼 '{name}'")
        if ast.where is not None:
            name = ast.where.column
            if name not in types:
                raise ValidationError(f"없는 컬럼 '{name}'")
            if not _type_ok(ast.where.value, types[name]):
                raise ValidationError(f"컬럼 '{name}'의 타입과 맞지 않음")
