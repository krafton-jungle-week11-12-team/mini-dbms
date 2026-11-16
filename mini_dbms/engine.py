"""문장 하나를 토크나이저 → 파서 → 검증 → 실행기 순서로 처리해요."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from mini_dbms.executor import Executor, Result
from mini_dbms.parser import parse
from mini_dbms.storage import Storage
from mini_dbms.tokenizer import tokenize
from mini_dbms.validator import validate

# Phase 1의 고정 스키마
SCHEMA = {
    "users": [("id", "INT"), ("name", "TEXT"), ("age", "INT")],
}


class Engine:
    def __init__(self, data_dir, schema=SCHEMA):
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self.schema = schema
        self.executor = Executor(Storage(data_dir, schema), schema)

    def execute(self, stmt: str) -> Optional[Result]:
        """빈 문장이면 None을 반환해요. 에러는 DbError 예외로 알려요."""
        ast = parse(tokenize(stmt))
        if ast is None:
            return None
        validate(ast, self.schema)
        return self.executor.run(ast)
