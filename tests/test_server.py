import http.client
import json
import threading

import pytest

from mini_dbms.engine import Engine
from mini_dbms.server import QueryServer

# id 1~3 행. 머리글 없이 데이터만 있어요.
THREE_USERS = "1,kim,25\n2,lee,30\n3,park,27\n"


@pytest.fixture
def start_server(tmp_path, write_csv):
    """tmp_path를 데이터 폴더로 서버를 띄우고 서버 객체를 돌려줘요.

    prep은 서버를 띄우기 전에 users.csv에 써 둘 내용이에요.
    엔진이 시작할 때 파일을 읽어 인덱스를 복구하므로, 데이터는 서버보다 먼저 써야 해요.
    """
    servers = []

    def _start(prep=""):
        write_csv(prep)
        server = QueryServer(("127.0.0.1", 0), Engine(tmp_path))
        # poll_interval 기본값(0.5초)이면 shutdown()이 테스트마다 0.5초씩 기다려요.
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        thread.start()
        servers.append((server, thread))
        return server

    yield _start

    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(server, method, path, body=None, headers=None):
    """요청을 보내고 (상태 코드, JSON 바디)를 돌려줘요.

    body가 dict면 JSON으로, str이면 그대로 UTF-8로 보내요.
    headers를 주지 않으면 바디가 있을 때 Content-Type을 application/json으로 붙여요.
    """
    host, port = server.server_address[:2]
    if isinstance(body, dict):
        body = json.dumps(body)
    if isinstance(body, str):
        body = body.encode("utf-8")
    if headers is None:
        headers = {"Content-Type": "application/json"} if body is not None else {}

    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read().decode("utf-8"))
    finally:
        conn.close()


def post_sql(server, sql):
    return request(server, "POST", "/query", {"sql": sql})


# ---------------------------------------------------------------------------
# 성공 응답
# ---------------------------------------------------------------------------


def test_select_success(start_server):
    """T-SRV-01 SELECT 성공"""
    server = start_server(THREE_USERS)

    status, body = post_sql(server, "SELECT * FROM users WHERE id = 3")

    assert status == 200
    assert body["ok"] is True
    assert body["type"] == "select"
    assert body["columns"] == ["id", "name", "age"]
    assert body["rows"] == [[3, "park", 27]]
    assert body["row_count"] == 1


def test_insert_success(start_server):
    """T-SRV-02 INSERT 성공"""
    server = start_server("")

    status, body = post_sql(server, "INSERT INTO users VALUES ('kim', 25)")

    assert status == 201
    assert body["ok"] is True
    assert body["type"] == "insert"
    assert body["inserted_id"] == 1
    assert body["affected_rows"] == 1


@pytest.mark.parametrize(
    "sql",
    [
        pytest.param("SELECT * FROM users;", id="T-SRV-03 끝의 세미콜론 허용"),
        pytest.param("SELECT * FROM users;;", id="T-SRV-03 끝의 세미콜론 여러 개"),
    ],
)
def test_trailing_semicolon(start_server, sql):
    server = start_server(THREE_USERS)

    status, body = post_sql(server, sql)

    assert status == 200
    assert body["ok"] is True
    assert body["row_count"] == 3


# ---------------------------------------------------------------------------
# 실패 응답: 요청 검사와 엔진 예외 변환
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, path, body, headers, status, code, message",
    [
        pytest.param(
            "POST", "/query", {"sql": "SELECT * FORM users"}, None,
            400, "SYNTAX_ERROR", None,
            id="T-SRV-04 SQL 문법 오류",
        ),
        pytest.param(
            "POST", "/query", {"sql": "SELECT * FROM orders"}, None,
            404, "TABLE_NOT_FOUND", "없는 테이블 'orders'",
            id="T-SRV-05 없는 테이블",
        ),
        pytest.param(
            "POST", "/abc", {"sql": "SELECT * FROM users"}, None,
            404, "NOT_FOUND", None,
            id="T-SRV-08 없는 경로",
        ),
        pytest.param(
            "GET", "/query", None, None,
            405, "METHOD_NOT_ALLOWED", None,
            id="T-SRV-09 POST가 아닌 메서드",
        ),
        pytest.param(
            "POST", "/query", "SELECT * FROM users", {"Content-Type": "text/plain"},
            415, "UNSUPPORTED_MEDIA_TYPE", None,
            id="T-SRV-10 JSON이 아닌 Content-Type",
        ),
        pytest.param(
            "POST", "/query", '{"sql": ', None,
            400, "INVALID_JSON", None,
            id="T-SRV-12 JSON 파싱 실패",
        ),
        pytest.param(
            "POST", "/query", {"query": "SELECT * FROM users"}, None,
            400, "INVALID_REQUEST", None,
            id="T-SRV-13 sql 필드 없음",
        ),
        pytest.param(
            "POST", "/query", {"sql": "SELECT * FROM users; SELECT * FROM users"}, None,
            400, "MULTIPLE_STATEMENTS", None,
            id="T-SRV-14 여러 문장",
        ),
    ],
)
def test_error_response(start_server, method, path, body, headers, status, code, message):
    server = start_server(THREE_USERS)

    actual_status, actual_body = request(server, method, path, body, headers)

    assert actual_status == status
    assert actual_body["ok"] is False
    assert actual_body["error"]["code"] == code
    if message is not None:
        assert actual_body["error"]["message"] == message


def test_payload_too_large(start_server):
    """T-SRV-11 바디 1MB 초과

    서버는 바디를 읽기 전에 Content-Length만 보고 거절해요.
    1MB를 실제로 보내면 서버가 먼저 연결을 닫아 클라이언트 쪽 전송이 실패할 수 있어서,
    헤더에 크기만 적고 바디는 보내지 않아요.
    """
    server = start_server("")
    host, port = server.server_address[:2]

    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        conn.putrequest("POST", "/query")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(1_048_577))
        conn.endheaders()
        resp = conn.getresponse()
        status, body = resp.status, json.loads(resp.read().decode("utf-8"))
    finally:
        conn.close()

    assert status == 413
    assert body["ok"] is False
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"


# ---------------------------------------------------------------------------
# 엔진 내부 오류와 복구
# ---------------------------------------------------------------------------

SECRET = "디스크가 가득 참: /secret/path"


def _broken_execute(sql):
    raise RuntimeError(SECRET)


def test_internal_error(start_server, monkeypatch, caplog):
    """T-SRV-06 엔진 내부 오류"""
    server = start_server(THREE_USERS)
    monkeypatch.setattr(server.engine, "execute", _broken_execute)

    status, body = post_sql(server, "SELECT * FROM users")

    assert status == 500
    assert body["ok"] is False
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "internal server error"
    # 응답에는 예외 내용이 없어야 해요.
    assert SECRET not in json.dumps(body, ensure_ascii=False)
    # 서버 로그에는 예외가 스택 트레이스와 함께 남아야 해요.
    assert any(
        record.exc_info is not None and SECRET in str(record.exc_info[1])
        for record in caplog.records
    )


def test_recovers_after_internal_error(start_server, monkeypatch):
    """T-SRV-07 실패 후 다음 요청 정상 처리"""
    server = start_server(THREE_USERS)
    monkeypatch.setattr(server.engine, "execute", _broken_execute)
    status, _ = post_sql(server, "SELECT * FROM users")
    assert status == 500

    monkeypatch.undo()
    status, body = post_sql(server, "SELECT * FROM users")

    assert status == 200
    assert body["ok"] is True
