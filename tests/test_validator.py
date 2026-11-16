import re

import pytest

from mini_dbms.parser import parse
from mini_dbms.tokenizer import tokenize
from mini_dbms.validator import ValidationError, validate


@pytest.mark.parametrize(
    "sql, message",
    [
        pytest.param("SELECT * FROM nope", "없는 테이블 'nope'",
                     id="T-VAL-01 없는 테이블"),
        pytest.param("SELECT * FROM users WHERE nope = 1", "없는 컬럼 'nope'",
                     id="T-VAL-02 없는 컬럼"),
        pytest.param("INSERT INTO users VALUES (1, 'kim')", "값 개수가 컬럼 수와 다름",
                     id="T-VAL-03 값 개수 다름"),
        pytest.param("INSERT INTO users VALUES ('a', 'kim', 25)", "컬럼 'id'의 타입과 맞지 않음",
                     id="T-VAL-04 값 타입 다름"),
    ],
)
def test_validate_error(schema, sql, message):
    with pytest.raises(ValidationError, match=re.escape(message)):
        validate(parse(tokenize(sql)), schema)
