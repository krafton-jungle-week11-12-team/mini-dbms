import re

import pytest

from mini_dbms.tokenizer import TokenizeError, tokenize

# 값이 없는 토큰은 종류만, 값이 있는 토큰은 (종류, 값)으로 비교해요.
LPAREN, RPAREN, COMMA, EOF = "LPAREN", "RPAREN", "COMMA", "EOF"
_NO_VALUE = {LPAREN, RPAREN, COMMA, EOF}


def KEYWORD(v):
    return ("KEYWORD", v)


def IDENT(v):
    return ("IDENT", v)


def NUMBER(v):
    return ("NUMBER", v)


def STRING(v):
    return ("STRING", v)


def SYMBOL(v):
    return ("SYMBOL", v)


def _simplify(tokens):
    return [t.type if t.type in _NO_VALUE else (t.type, t.value) for t in tokens]


def _contains(seq, sub):
    n = len(sub)
    return any(seq[i : i + n] == sub for i in range(len(seq) - n + 1))


@pytest.mark.parametrize(
    "sql, expected",
    [
        pytest.param(
            "InsErt into users values(1, 'kim', 23)",
            [KEYWORD("INSERT"), KEYWORD("INTO"), IDENT("users"), KEYWORD("VALUES"),
             LPAREN, NUMBER(1), COMMA, STRING("kim"), COMMA, NUMBER(23), RPAREN, EOF],
            id="T-TOK-01 키워드 대소문자 섞임",
        ),
        pytest.param(
            "insert into users values(1, 'k;i@m', 23)",
            [..., COMMA, STRING("k;i@m"), COMMA, ...],
            id="T-TOK-02 문자열 안의 ; @",
        ),
        pytest.param(
            "insert into users values(1, 'kim', -23)",
            [..., COMMA, NUMBER(-23), RPAREN, EOF],
            id="T-TOK-03 음수",
        ),
        pytest.param(
            "select * from users where id=-5",
            [..., IDENT("id"), SYMBOL("="), NUMBER(-5), EOF],
            id="T-TOK-04 공백 없는 비교",
        ),
        pytest.param(
            "select * from users where id != 5",
            [..., IDENT("id"), SYMBOL("!="), NUMBER(5), EOF],
            id="T-TOK-05 !=",
        ),
        pytest.param(
            "select * from users where age <= 20",
            [..., IDENT("age"), SYMBOL("<="), NUMBER(20), EOF],
            id="T-TOK-06 <= 한 토큰",
        ),
    ],
)
def test_tokenize(sql, expected):
    actual = _simplify(tokenize(sql))
    if expected[0] is ...:
        # [..., a, b, ...] 는 그 구간이 연속으로 들어 있는지만 봐요.
        sub = [t for t in expected if t is not ...]
        assert _contains(actual, sub), actual
    else:
        assert actual == expected


@pytest.mark.parametrize(
    "sql, message",
    [
        pytest.param("select * from users where id = @1", "알 수 없는 문자 '@'",
                     id="T-TOK-07 모르는 문자"),
        pytest.param('insert into users values(1, "kim", 23)', "알 수 없는 문자 '\"'",
                     id="T-TOK-08 큰따옴표"),
        pytest.param("select * from users where id ! 5", "'!' 뒤에는 '='가 와야 함",
                     id="T-TOK-09 ! 단독"),
        pytest.param("select * from users where age = - 5", "'-' 뒤에는 숫자가 와야 함",
                     id="T-TOK-10 - 뒤에 숫자 없음"),
        pytest.param("insert into users values(12abc, 'kim', 23)", "잘못된 숫자 '12abc'",
                     id="T-TOK-11 숫자 뒤에 문자"),
        pytest.param("insert into users values(1, 'kim, 23)", "닫히지 않은 문자열",
                     id="T-TOK-12 닫히지 않은 문자열"),
        pytest.param("insert into users values(1, 'kim', -23.1)", "알 수 없는 문자 '.'",
                     id="T-TOK-13 소수점"),
    ],
)
def test_tokenize_error(sql, message):
    # 메시지 뒤에 붙는 위치 정보((2행 15열) 등)는 비교하지 않아요.
    with pytest.raises(TokenizeError, match=re.escape(message)):
        tokenize(sql)
