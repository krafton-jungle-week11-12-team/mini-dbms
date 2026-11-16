"""SQL 파일을 읽어 문장마다 실행하고 결과를 표로 출력해요."""

from __future__ import annotations

import os
import sys
import unicodedata

from mini_dbms.engine import Engine
from mini_dbms.errors import DbError
from mini_dbms.executor import Result

USAGE = "사용법: mini-dbms <SQL 파일>"


def split_statements(sql: str) -> list[str]:
    stmts, buf, in_quote = [], [], False
    for ch in sql:
        if ch == "'":
            in_quote = not in_quote
        if ch == ";" and not in_quote:
            stmts.append("".join(buf))  # 빈 문장도 그대로 전달
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        stmts.append("".join(buf))  # 따옴표가 안 닫혔어도 그대로 전달
    return stmts


def print_table(result: Result, out=sys.stdout) -> None:
    if not result.columns:
        print(f"{result.affected}행 삽입", file=out)
        return
    cells = [[str(v) for v in row] for row in result.rows]
    widths = [
        max([_width(c)] + [_width(row[i]) for row in cells])
        for i, c in enumerate(result.columns)
    ]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt(values):
        return "| " + " | ".join(v + " " * (w - _width(v)) for v, w in zip(values, widths)) + " |"

    print(line, file=out)
    print(fmt(result.columns), file=out)
    print(line, file=out)
    for row in cells:
        print(fmt(row), file=out)
    if cells:
        print(line, file=out)
    print(f"({result.affected}행)", file=out)


def _width(s: str) -> int:
    """한글처럼 넓은 글자는 2칸으로 세요."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _error(msg: str) -> int:
    print(f"에러: {msg}", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        return _error(USAGE)

    path = argv[0]
    try:
        with open(path, encoding="utf-8") as f:
            sql = f.read()
    except FileNotFoundError:
        return _error(f"파일이 없음 '{path}'")
    except (OSError, UnicodeDecodeError) as e:
        return _error(f"파일을 읽을 수 없음 '{path}': {e}")
    if not sql.strip():
        return _error(f"빈 파일 '{path}'")

    engine = Engine(os.environ.get("MINI_DBMS_DATA", "data"))
    status = 0
    for n, stmt in enumerate(split_statements(sql), start=1):
        try:
            result = engine.execute(stmt)
        except DbError as e:
            # 앞 문장이 실패해도 다음 문장은 계속 실행해요.
            print(f"에러: {n}번째 문장: {e}", file=sys.stderr)
            status = 1
            continue
        if result is not None:
            print_table(result)
    return status
