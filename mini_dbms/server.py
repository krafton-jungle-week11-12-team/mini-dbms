"""POST /query로 받은 SQL 한 문장을 엔진에 넘기고 결과를 JSON으로 응답해요.

서버는 HTTP 요청 형식만 검사해요. 문법, 테이블, 값 검사는 엔진이 해요.
요청 검사 순서와 상태 코드는 docs/design/phase3.md를 따라요.

메인 스레드는 연결을 받아 작업 큐에 넣기만 하고, 워커 스레드가 요청을 처리해요.
스레드 풀 구조는 docs/design/phase4.md를 따라요.

실행: python -m mini_dbms.server [--host HOST] [--port PORT] [--workers N] [--queue-size M]
데이터 폴더는 CLI와 같이 MINI_DBMS_DATA 환경 변수(기본 data)를 써요.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import threading
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


def _build_busy_response() -> bytes:
    body = json.dumps(
        {"ok": False, "error": {"code": "SERVICE_UNAVAILABLE", "message": "server is busy"}}
    ).encode("utf-8")
    head = (
        "HTTP/1.0 503 Service Unavailable\r\n"
        "Content-Type: application/json; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Retry-After: 1\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    return head + body


# 작업 큐가 가득 찼을 때 메인 스레드가 그대로 보내는 응답이에요.
BUSY_RESPONSE = _build_busy_response()


class RequestError(Exception):
    """요청 검사 실패. 상태 코드와 error.code를 담아요."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class QueryServer(HTTPServer):
    """메인 스레드는 연결을 작업 큐에 넣고, 워커 스레드 N개가 꺼내서 처리해요."""

    def __init__(self, server_address, engine: Engine, workers: int = 4, queue_size: int = 16):
        # queue_size=0은 크기 제한이 없다는 뜻이라 503 거절이 동작하지 않아요.
        if workers < 1 or queue_size < 1:
            raise ValueError("workers와 queue_size는 1 이상이어야 해요")
        super().__init__(server_address, QueryHandler)
        self.engine = engine
        self.jobs = queue.Queue(maxsize=queue_size)  # 작업 큐
        self.workers = [  # 워커 목록
            threading.Thread(target=self._worker, name=f"worker-{i}")
            for i in range(1, workers + 1)
        ]
        for t in self.workers:
            t.start()

    # ------------------------------------------------------------------
    # 메인 스레드
    # ------------------------------------------------------------------

    def process_request(self, request, client_address) -> None:
        """연결을 작업 큐에 넣기만 해요. 가득 찼으면 503으로 거절해요."""
        try:
            self.jobs.put_nowait((request, client_address))
        except queue.Full:
            self._reject(request)

    def _reject(self, request) -> None:
        """요청을 끝까지 읽지 않고, 이미 도착한 데이터만 비운 뒤 503을 보내고 닫아요."""
        try:
            request.setblocking(False)
            try:
                while request.recv(65536):
                    pass
            except (BlockingIOError, InterruptedError):
                pass
            request.setblocking(True)
            request.sendall(BUSY_RESPONSE)
        except OSError:
            pass
        finally:
            self.shutdown_request(request)

    # ------------------------------------------------------------------
    # 워커 스레드
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        while True:
            job = self.jobs.get()  # 큐가 비어 있으면 여기서 기다려요.
            if job is None:  # 종료 신호
                return
            request, client_address = job
            try:
                self.finish_request(request, client_address)
            except Exception:
                self.handle_error(request, client_address)
            finally:
                self.shutdown_request(request)

    def handle_error(self, request, client_address) -> None:
        logger.exception("요청 처리 중 오류: client=%s", client_address)

    def server_close(self) -> None:
        # bind()가 실패하면 부모 __init__이 워커를 만들기 전에 이 메서드를 불러요.
        workers = getattr(self, "workers", [])
        for _ in workers:
            self.jobs.put(None)
        for t in workers:
            t.join()
        super().server_close()


class QueryHandler(BaseHTTPRequestHandler):
    # 바디를 보내지 않는 클라이언트가 워커를 오래 붙잡지 않게 해요.
    # 전체 시간이 아니라 한 번 읽거나 쓸 때마다 기다리는 최대 시간이에요.
    timeout = 5

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
                "index_column": result.index_column,
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
    parser.add_argument("--workers", type=int, default=4, help="워커 스레드 수 (1 이상)")
    parser.add_argument("--queue-size", type=int, default=16, help="작업 큐 크기 (1 이상)")
    args = parser.parse_args(argv)

    if args.workers < 1 or args.queue_size < 1:
        parser.error("--workers와 --queue-size는 1 이상이어야 해요")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = Engine(os.environ.get("MINI_DBMS_DATA", "data"))
    server = QueryServer(
        (args.host, args.port), engine, workers=args.workers, queue_size=args.queue_size
    )
    logger.info("listening on http://%s:%d%s", args.host, args.port, QUERY_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
