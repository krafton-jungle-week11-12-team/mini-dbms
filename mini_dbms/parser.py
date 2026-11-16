"""토큰 목록을 AST로 만들어요."""

from __future__ import annotations

from typing import Optional, Union

from mini_dbms.errors import ParseError, josa
from mini_dbms.nodes import Condition, InsertStmt, SelectStmt, Value
from mini_dbms.tokenizer import Token

OPERATORS = {"=", "!=", "<", ">", "<=", ">="}

__all__ = ["ParseError", "parse"]


def parse(tokens: list[Token]) -> Optional[Union[InsertStmt, SelectStmt]]:
    """빈 문장이면 None을 반환해요."""
    return _Parser(tokens).parse()


def _expected(what: str, got: Token) -> ParseError:
    shown = got.display()
    return ParseError(
        f"{what}{josa(what, '이', '가')} 필요한데 {shown}{josa(shown, '이', '가')} 옴"
        f" ({got.line}행 {got.col}열)"
    )


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    @property
    def cur(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        tok = self.cur
        if tok.type != "EOF":
            self.pos += 1
        return tok

    def _is(self, type_: str, value=None) -> bool:
        return self.cur.type == type_ and (value is None or self.cur.value == value)

    def _expect_keyword(self, kw: str) -> None:
        if not self._is("KEYWORD", kw):
            raise _expected(kw, self.cur)
        self._advance()

    def _expect(self, type_: str, value: str) -> None:
        if not self._is(type_, value):
            raise _expected(f"'{value}'", self.cur)
        self._advance()

    def _ident(self, what: str) -> str:
        if not self._is("IDENT"):
            raise _expected(what, self.cur)
        return self._advance().value

    def _value(self) -> Value:
        if self.cur.type in ("NUMBER", "STRING"):
            return self._advance().value
        raise _expected("값", self.cur)

    def _end(self) -> None:
        if not self._is("EOF"):
            shown = self.cur.display()
            raise ParseError(
                f"문장 끝이어야 하는데 {shown}{josa(shown, '이', '가')} 옴"
                f" ({self.cur.line}행 {self.cur.col}열)"
            )

    def parse(self):
        if self._is("EOF"):
            return None
        if self._is("KEYWORD", "INSERT"):
            return self._insert()
        if self._is("KEYWORD", "SELECT"):
            return self._select()
        raise ParseError(
            f"문장은 INSERT 또는 SELECT로 시작해야 함 ({self.cur.line}행 {self.cur.col}열)"
        )

    def _insert(self) -> InsertStmt:
        self._expect_keyword("INSERT")
        self._expect_keyword("INTO")
        table = self._ident("테이블 이름")
        self._expect_keyword("VALUES")
        self._expect("LPAREN", "(")
        values = [self._value()]
        while True:
            if self._is("COMMA"):
                self._advance()
                values.append(self._value())
            elif self._is("RPAREN"):
                self._advance()
                break
            elif self._is("EOF"):
                raise _expected("')'", self.cur)
            else:
                shown = self.cur.display()
                raise ParseError(
                    f"','나 ')'가 필요한데 {shown}{josa(shown, '이', '가')} 옴"
                    f" ({self.cur.line}행 {self.cur.col}열)"
                )
        self._end()
        return InsertStmt(table, values)

    def _select(self) -> SelectStmt:
        self._expect_keyword("SELECT")
        if self._is("SYMBOL", "*"):
            self._advance()
            columns = None
        else:
            columns = [self._ident("컬럼 이름")]
            while self._is("COMMA"):
                self._advance()
                columns.append(self._ident("컬럼 이름"))
        self._expect_keyword("FROM")
        table = self._ident("테이블 이름")
        where = None
        if self._is("KEYWORD", "WHERE"):
            self._advance()
            where = self._condition()
        self._end()
        return SelectStmt(table, columns, where)

    def _condition(self) -> Condition:
        column = self._ident("컬럼 이름")
        if not (self.cur.type == "SYMBOL" and self.cur.value in OPERATORS):
            raise _expected("연산자", self.cur)
        op = self._advance().value
        return Condition(column, op, self._value())
