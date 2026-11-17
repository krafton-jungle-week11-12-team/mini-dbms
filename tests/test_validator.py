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
    ],
)
def test_validate_error(schema, sql, message):
    with pytest.raises(ValidationError, match=re.escape(message)):
        validate(parse(tokenize(sql)), schema)
