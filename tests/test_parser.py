import re

import pytest

from mini_dbms.nodes import Condition, InsertStmt, SelectStmt
from mini_dbms.parser import ParseError, parse
from mini_dbms.tokenizer import tokenize


@pytest.mark.parametrize(
    "sql, expected",
    [
        pytest.param(
            "INSERT INTO users VALUES (1, 'kim', 25)",
            InsertStmt(table="users", values=[1, "kim", 25]),
            id="T-PAR-01 INSERT",
        ),
        pytest.param(
            "SELECT * FROM users",
            SelectStmt(table="users", columns=None, where=None),
            id="T-PAR-02 SELECT *",
        ),
        pytest.param(
            "SELECT name, age FROM users WHERE age >= 20",
            SelectStmt(
                table="users",
                columns=["name", "age"],
                where=Condition(column="age", op=">=", value=20),
            ),
            id="T-PAR-03 SELECT 컬럼 + WHERE",
        ),
        pytest.param("", None, id="T-PAR-04 빈 문장 무시"),
    ],
)
def test_parse(sql, expected):
    assert parse(tokenize(sql)) == expected


@pytest.mark.parametrize(
    "sql, message",
    [
        pytest.param("INSERT INTO users VALUE (1)", "VALUES가 필요한데 'VALUE'가 옴",
                     id="T-PAR-05 키워드 오타"),
        pytest.param("SELEC * FROM users", "문장은 INSERT 또는 SELECT로 시작해야 함",
                     id="T-PAR-06 시작 키워드 아님"),
        pytest.param("SELECT * users", "FROM이 필요한데 'users'가 옴",
                     id="T-PAR-07 키워드 누락"),
        pytest.param("INSERT INTO users VALUES (1, 2", "')'가 필요한데 EOF가 옴",
                     id="T-PAR-08 닫는 괄호 누락"),
        pytest.param("INSERT INTO users VALUES (1 2)", "','나 ')'가 필요한데 '2'가 옴",
                     id="T-PAR-09 쉼표 누락"),
        pytest.param("SELECT * FROM users WHERE age = name", "값이 필요한데 'name'이 옴",
                     id="T-PAR-10 값 자리에 식별자"),
        pytest.param("SELECT * FROM users abc", "문장 끝이어야 하는데 'abc'가 옴",
                     id="T-PAR-11 남은 토큰"),
    ],
)
def test_parse_error(sql, message):
    with pytest.raises(ParseError, match=re.escape(message)):
        parse(tokenize(sql))
