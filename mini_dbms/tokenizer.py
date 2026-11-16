"""SQL 문장 하나를 토큰 목록으로 잘라요."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from mini_dbms.errors import TokenizeError

KEYWORDS = {"INSERT", "INTO", "VALUES", "SELECT", "FROM", "WHERE"}
SINGLE = {"(": "LPAREN", ")": "RPAREN", ",": "COMMA", "*": "SYMBOL",
          "=": "SYMBOL", "<": "SYMBOL", ">": "SYMBOL"}
DOUBLE = {"!=", "<=", ">="}

__all__ = ["Token", "TokenizeError", "tokenize"]


@dataclass
class Token:
    type: str  # KEYWORD IDENT NUMBER STRING SYMBOL LPAREN RPAREN COMMA EOF
    value: Union[str, int, None]
    line: int
    col: int

    def display(self) -> str:
        """에러 메시지에 쓰는 모습. 예: 'users', EOF"""
        return "EOF" if self.type == "EOF" else f"'{self.value}'"


def _is_word_start(ch: str) -> bool:
    return ch == "_" or ("a" <= ch.lower() <= "z")


def _is_word_char(ch: str) -> bool:
    return _is_word_start(ch) or ch.isdigit()


def tokenize(sql: str) -> list[Token]:
    tokens: list[Token] = []
    i, line, line_start = 0, 1, 0
    n = len(sql)

    while i < n:
        ch = sql[i]
        col = i - line_start + 1

        if ch == "\n":
            i += 1
            line, line_start = line + 1, i
            continue
        if ch.isspace():
            i += 1
            continue

        if _is_word_start(ch):
            start = i
            while i < n and _is_word_char(sql[i]):
                i += 1
            word = sql[start:i]
            if word.upper() in KEYWORDS:
                tokens.append(Token("KEYWORD", word.upper(), line, col))
            else:
                tokens.append(Token("IDENT", word, line, col))
            continue

        if ch.isdigit() or ch == "-":
            start = i
            if ch == "-":
                if i + 1 >= n or not sql[i + 1].isdigit():
                    raise TokenizeError(f"'-' 뒤에는 숫자가 와야 함 ({line}행 {col}열)")
                i += 1
            while i < n and sql[i].isdigit():
                i += 1
            if i < n and _is_word_start(sql[i]):
                while i < n and _is_word_char(sql[i]):
                    i += 1
                raise TokenizeError(f"잘못된 숫자 '{sql[start:i]}' ({line}행 {col}열)")
            tokens.append(Token("NUMBER", int(sql[start:i]), line, col))
            continue

        if ch == "'":
            start_line = line
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise TokenizeError(f"닫히지 않은 문자열 ({start_line}행에서 시작)")
                c = sql[i]
                if c == "'":
                    if i + 1 < n and sql[i + 1] == "'":  # '' 는 ' 하나
                        buf.append("'")
                        i += 2
                        continue
                    i += 1
                    break
                if c == "\n":
                    line, line_start = line + 1, i + 1
                buf.append(c)
                i += 1
            tokens.append(Token("STRING", "".join(buf), start_line, col))
            continue

        two = sql[i : i + 2]
        if two in DOUBLE:
            tokens.append(Token("SYMBOL", two, line, col))
            i += 2
            continue
        if ch == "!":
            raise TokenizeError(f"'!' 뒤에는 '='가 와야 함 ({line}행 {col}열)")
        if ch in SINGLE:
            tokens.append(Token(SINGLE[ch], ch, line, col))
            i += 1
            continue

        raise TokenizeError(f"알 수 없는 문자 '{ch}' ({line}행 {col}열)")

    tokens.append(Token("EOF", None, line, i - line_start + 1))
    return tokens
