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
    "messages": [("id", "INT"), ("author", "TEXT"), ("content", "TEXT"), ("created_at", "INT"), ("client_id", "TEXT")],
    "likes": [("id", "INT"), ("message_id", "INT"), ("created_at", "INT")],
}

# 테이블별 인덱스 컬럼. 이 컬럼 값은 실행기가 자동 부여해요.
INDEX_KEYS = {"users": "id", "messages": "id", "likes": "id"}

# 테이블별 보조 인덱스 컬럼. 값이 중복될 수 있고, WHERE <컬럼> = ? 조회에 써요.
SECONDARY_INDEXES = {"messages": ["client_id"]}


class Engine:
    def __init__(
        self, data_dir, schema=SCHEMA, index_keys=INDEX_KEYS,
        secondary_indexes=SECONDARY_INDEXES,
    ):
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self.schema = schema
        self.index_keys = index_keys
        self.executor = Executor(
            Storage(data_dir, schema), schema, index_keys, secondary_indexes,
        )

    def execute(self, stmt: str) -> Optional[Result]:
        """빈 문장이면 None을 반환해요. 에러는 DbError 예외로 알려요."""
        ast = parse(tokenize(stmt))
        if ast is None:
            return None
        validate(ast, self.schema, self.index_keys)
        return self.executor.run(ast)
