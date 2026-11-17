"""POST /query로 받은 SQL 한 문장을 엔진에 넘기고 결과를 JSON으로 응답해요.

서버는 HTTP 요청 형식만 검사해요. 문법, 테이블, 값 검사는 엔진이 해요.
요청 검사 순서와 상태 코드는 docs/design/phase3.md를 따라요.

실행: python -m mini_dbms.server [--host HOST] [--port PORT]
데이터 폴더는 CLI와 같이 MINI_DBMS_DATA 환경 변수(기본 data)를 써요.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

from mini_dbms.cli import split_statements
from mini_dbms.engine import Engine
from mini_dbms.errors import (
    DbError,
    ParseError,
    TableNotFoundError,
    TokenizeError,
    ValidationError,
)

logger = logging.getLogger(__name__)

QUERY_PATH = "/query"
MAX_BODY_BYTES = 1024 * 1024  # 1MB


class RequestError(Exception):
    """요청 검사 실패. 상태 코드와 error.code를 담아요."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class QueryServer(HTTPServer):
    """요청을 하나씩 순서대로 처리하는 서버예요. 워커 풀은 아직 붙이지 않았어요."""

    def __init__(self, server_address, engine: Engine):
        super().__init__(server_address, QueryHandler)
        self.engine = engine


class QueryHandler(BaseHTTPRequestHandler):
    # 바디를 보내지 않는 클라이언트가 서버를 계속 붙잡지 않게 해요.
    timeout = 10

    def _handle(self) -> None:
        self._body_read = False
        try:
            sql = self._read_sql()
        except RequestError as e:
            self._send_error(e.status, e.code, e.message)
            return
        self._execute(sql)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _handle

    # ------------------------------------------------------------------
    # 요청 검사 (설계 문서의 1~13번)
    # ------------------------------------------------------------------

    def _read_sql(self) -> str:
        if urlsplit(self.path).path != QUERY_PATH:
            raise RequestError(404, "NOT_FOUND", f"없는 경로 '{self.path}'")
        if self.command != "POST":
            raise RequestError(405, "METHOD_NOT_ALLOWED", "POST만 허용해요")

        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";")[0].strip().lower() != "application/json":
            raise RequestError(
                415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type은 application/json이어야 해요"
            )

        length = self._content_length()
        if length is None:
            raise RequestError(411, "LENGTH_REQUIRED", "Content-Length 헤더가 필요해요")
        if length < 0:
            raise RequestError(400, "INVALID_REQUEST", "Content-Length가 0 이상의 정수가 아니에요")
        if length > MAX_BODY_BYTES:
            raise RequestError(413, "PAYLOAD_TOO_LARGE", "바디는 1MB를 넘을 수 없어요")

        raw = self.rfile.read(length)
        self._body_read = True

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise RequestError(400, "INVALID_REQUEST", "바디가 UTF-8이 아니에요") from None
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            raise RequestError(400, "INVALID_JSON", "바디가 올바른 JSON이 아니에요") from None
        if not isinstance(body, dict):
            raise RequestError(400, "INVALID_REQUEST", "바디는 JSON 객체여야 해요")
        if "sql" not in body:
            raise RequestError(400, "INVALID_REQUEST", "'sql' 필드가 필요해요")
        sql = body["sql"]
        if not isinstance(sql, str):
            raise RequestError(400, "INVALID_REQUEST", "'sql'은 문자열이어야 해요")

        # 끝의 ;가 여러 개여도 빈 문장을 빼면 한 문장이에요.
        stmts = [s for s in split_statements(sql) if s.strip()]
        if not stmts:
            raise RequestError(400, "EMPTY_SQL", "SQL이 비어 있어요")
        if len(stmts) > 1:
            raise RequestError(400, "MULTIPLE_STATEMENTS", "SQL은 한 문장만 보낼 수 있어요")
        return stmts[0]

    def _content_length(self):
        """헤더가 없으면 None, 0 이상의 정수가 아니면 -1을 돌려줘요."""
        value = self.headers.get("Content-Length")
        if value is None:
            return None
        value = value.strip()
        return int(value) if value.isdigit() else -1

    # ------------------------------------------------------------------
    # 엔진 호출과 예외 변환
    # ------------------------------------------------------------------

    def _execute(self, sql: str) -> None:
        try:
            start = time.perf_counter()
            result = self.server.engine.execute(sql)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        except TableNotFoundError as e:  # ValidationError의 자식이라 먼저 잡아요.
            self._send_error(404, "TABLE_NOT_FOUND", str(e))
            return
        except (TokenizeError, ParseError) as e:
            self._send_error(400, "SYNTAX_ERROR", str(e))
            return
        except (ValidationError, DbError) as e:
            self._send_error(400, "INVALID_VALUE", str(e))
            return
        except Exception:
            # 예외 상세는 로그에만 남기고 클라이언트에는 보내지 않아요.
            logger.exception("엔진 내부 오류: sql=%r", sql)
            self._send_error(500, "INTERNAL_ERROR", "internal server error")
            return

        if result is None:  # 검사에서 빈 문장을 걸렀으므로 오지 않아요.
            self._send_error(400, "EMPTY_SQL", "SQL이 비어 있어요")
            return

        if result.type == "insert":
            self._send_json(201, {
                "ok": True,
                "type": "insert",
                "inserted_id": result.inserted_id,
                "affected_rows": result.affected,
                "elapsed_ms": elapsed_ms,
            })
        else:
            self._send_json(200, {
                "ok": True,
                "type": "select",
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.affected,
                "used_index": result.used_index,
                "elapsed_ms": elapsed_ms,
            })

    # ------------------------------------------------------------------
    # 응답
    # ------------------------------------------------------------------

    def _send_error(self, status: int, code: str, message: str) -> None:
        self._discard_body()
        self._send_json(status, {"ok": False, "error": {"code": code, "message": message}})

    def _discard_body(self) -> None:
        """읽지 않은 바디를 비워요.

        받은 데이터를 남긴 채 소켓을 닫으면 OS가 RST를 보내서
        클라이언트가 응답을 읽기 전에 연결이 끊길 수 있어요.
        1MB를 넘는 바디는 읽지 않는다는 규칙은 그대로 지켜요.
        """
        if self._body_read:
            return
        self._body_read = True
        length = self._content_length()
        if length is not None and 0 < length <= MAX_BODY_BYTES:
            try:
                self.rfile.read(length)
            except OSError:
                pass

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args) -> None:
        # 접근 로그를 stderr 대신 logging으로 보내요.
        logger.info("%s - %s", self.address_string(), format % args)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="mini-dbms API 서버")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = Engine(os.environ.get("MINI_DBMS_DATA", "data"))
    server = QueryServer((args.host, args.port), engine)
    logger.info("listening on http://%s:%d%s", args.host, args.port, QUERY_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
