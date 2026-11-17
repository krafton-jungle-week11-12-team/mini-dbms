import http.client
import json
import socket
import threading
import time

import pytest

from mini_dbms.engine import Engine
from mini_dbms.server import QueryHandler, QueryServer

# id 1~3 행. 머리글 없이 데이터만 있어요.
THREE_USERS = "1,kim,25\n2,lee,30\n3,park,27\n"


@pytest.fixture
def start_server(tmp_path, write_csv):
    """tmp_path를 데이터 폴더로 서버를 띄우고 서버 객체를 돌려줘요.

    prep은 서버를 띄우기 전에 users.csv에 써 둘 내용이에요.
    엔진이 시작할 때 파일을 읽어 인덱스를 복구하므로, 데이터는 서버보다 먼저 써야 해요.
    나머지 키워드 인자(workers, queue_size)는 QueryServer에 그대로 넘겨요.
    """
    servers = []

    def _start(prep="", **kwargs):
        write_csv(prep)
        server = QueryServer(("127.0.0.1", 0), Engine(tmp_path), **kwargs)
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


# ---------------------------------------------------------------------------
# Phase 4: 스레드 풀
# ---------------------------------------------------------------------------


def wait_until(condition, timeout=2.0):
    """condition()이 참이 될 때까지 기다려요. 시간 안에 참이 되지 않으면 실패해요."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("조건이 시간 안에 참이 되지 않았어요")
        time.sleep(0.01)


def track_accepts(server):
    """메인 스레드가 process_request()로 넘긴 연결 수를 셀 수 있게 해요.

    qsize()가 0인 것만으로는 워커가 연결을 가져간 건지,
    아직 accept()하지 않은 건지 구분할 수 없어서 같이 봐요.
    """
    accepted = []
    original = server.process_request

    def _process_request(request, client_address):
        original(request, client_address)
        accepted.append(client_address)

    server.process_request = _process_request
    return accepted


def open_stalled(server):
    """POST /query 헤더와 Content-Length: 10만 보내고 바디는 보내지 않는 연결을 열어요."""
    sock = socket.create_connection(server.server_address[:2], timeout=5)
    sock.sendall(
        b"POST /query HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: 10\r\n"
        b"\r\n"
    )
    return sock


def post_in_thread(server, sql):
    """요청을 다른 스레드에서 보내요. 결과는 돌려준 리스트에 (상태 코드, 바디)로 담겨요."""
    result = []
    thread = threading.Thread(
        target=lambda: result.append(post_sql(server, sql)), daemon=True
    )
    thread.start()
    return thread, result


def test_main_thread_puts_jobs(start_server):
    """T-TP-01 메인 스레드는 작업을 큐에 넣는다"""
    server = start_server(THREE_USERS, workers=1, queue_size=4)
    accepted = track_accepts(server)
    a = open_stalled(server)
    wait_until(lambda: len(accepted) == 1 and server.jobs.qsize() == 0)

    b, b_result = post_in_thread(server, "SELECT * FROM users")
    c, c_result = post_in_thread(server, "SELECT * FROM users")

    wait_until(lambda: len(accepted) == 3)
    assert server.jobs.qsize() == 2
    assert b_result == [] and c_result == []

    a.close()
    b.join(timeout=5)
    c.join(timeout=5)
    assert b_result[0][0] == 200
    assert c_result[0][0] == 200


def test_job_waits_in_queue(start_server):
    """T-TP-02 놀고 있는 워커가 없으면 요청이 작업 큐에서 기다린다"""
    server = start_server(THREE_USERS, workers=1, queue_size=4)
    accepted = track_accepts(server)
    a = open_stalled(server)
    wait_until(lambda: len(accepted) == 1 and server.jobs.qsize() == 0)

    b, b_result = post_in_thread(server, "SELECT * FROM users")
    time.sleep(0.5)

    assert b.is_alive()
    assert b_result == []

    a.close()
    b.join(timeout=5)
    assert b_result[0][0] == 200


def test_reject_when_queue_full(start_server):
    """T-TP-03 작업 큐가 가득 찼다면 503을 응답한다"""
    server = start_server(THREE_USERS, workers=1, queue_size=1)
    accepted = track_accepts(server)
    a = open_stalled(server)
    wait_until(lambda: len(accepted) == 1 and server.jobs.qsize() == 0)
    b = open_stalled(server)
    wait_until(lambda: len(accepted) == 2 and server.jobs.qsize() == 1)

    host, port = server.server_address[:2]
    conn = http.client.HTTPConnection(host, port, timeout=1)
    try:
        start = time.monotonic()
        conn.request(
            "POST", "/query",
            body=json.dumps({"sql": "SELECT * FROM users"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        status, retry_after = resp.status, resp.getheader("Retry-After")
        body = json.loads(resp.read().decode("utf-8"))
        elapsed = time.monotonic() - start
    finally:
        conn.close()

    assert status == 503
    assert elapsed < 1
    assert body["ok"] is False
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert retry_after == "1"

    a.close()
    b.close()
    # 워커가 B를 큐에서 꺼내기 전에 보내면 큐가 아직 가득 차 있어서 다시 503이 와요.
    wait_until(lambda: server.jobs.qsize() == 0)
    status, _ = post_sql(server, "SELECT * FROM users")
    assert status == 200


def test_worker_survives_exception(start_server, monkeypatch, caplog):
    """T-TP-04 요청 처리 중 예외가 나도 워커가 스레드 풀로 돌아간다

    엔진 예외는 _execute가 500으로 바꾸므로, 핸들러 밖으로 나가는 예외를 일부러 만들어요.
    """
    server = start_server(THREE_USERS, workers=1)

    def _broken_execute(self, sql):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(QueryHandler, "_execute", _broken_execute)
    with pytest.raises(http.client.RemoteDisconnected):
        post_sql(server, "SELECT * FROM users")
    assert any(
        record.exc_info is not None and isinstance(record.exc_info[1], RuntimeError)
        for record in caplog.records
    )

    monkeypatch.undo()
    status, body = post_sql(server, "SELECT * FROM users")

    assert status == 200
    assert body["ok"] is True
    assert server.workers[0].is_alive()


def test_read_timeout_closes_connection(start_server, monkeypatch):
    """T-TP-05 요청을 읽을 때 정해진 시간 동안 데이터가 오지 않으면 연결을 닫는다

    실제 값은 5초지만 테스트 시간을 줄이려고 0.5초로 바꿔요.
    """
    monkeypatch.setattr(QueryHandler, "timeout", 0.5)
    server = start_server(THREE_USERS)
    sock = open_stalled(server)
    try:
        start = time.monotonic()
        data = sock.recv(1024)
        elapsed = time.monotonic() - start
    finally:
        sock.close()

    assert data == b""  # 응답(503 포함) 없이 닫힘
    assert 0.3 < elapsed < 2

    status, _ = post_sql(server, "SELECT * FROM users")
    assert status == 200


# ---------------------------------------------------------------------------
# Phase 4: 동시 요청과 테이블 락
# ---------------------------------------------------------------------------


def test_concurrent_inserts_unique_ids(start_server):
    """T-LK-01 INSERT를 동시에 여러 번 보내도 id가 겹치지 않는다

    두 번만 보내면 경합이 거의 생기지 않아서 200번 보내요.
    동시 요청 8개는 워커와 큐 크기의 합(20)보다 작아서 503이 나지 않아요.
    """
    server = start_server("", workers=4)
    results = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(8)

    def _insert_many():
        barrier.wait()
        for _ in range(25):
            result = post_sql(server, "INSERT INTO users VALUES ('kim', 25)")
            with results_lock:
                results.append(result)

    threads = [threading.Thread(target=_insert_many) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 200
    assert all(status == 201 for status, _ in results)
    assert sorted(body["inserted_id"] for _, body in results) == list(range(1, 201))

    status, body = post_sql(server, "SELECT * FROM users")
    assert status == 200
    assert body["row_count"] == 200
    for n in range(1, 201):
        status, body = post_sql(server, f"SELECT * FROM users WHERE id = {n}")
        assert status == 200
        assert body["rows"] == [[n, "kim", 25]]


def test_select_never_reads_partial_row(start_server, monkeypatch):
    """T-LK-02 INSERT 도중 SELECT해도 반쯤 써진 행을 읽지 않는다

    한 줄은 write() 한 번에 써져서 그대로는 경합이 거의 생기지 않아요.
    한 줄을 두 번에 나눠 쓰고 그 사이에 쉬어서 끼어들 틈을 일부러 만들어요.
    """
    server = start_server(THREE_USERS)
    storage = server.engine.executor.storage

    def _slow_append(table, record):
        data = storage._encode(record)
        half = len(data) // 2
        with open(storage._path(table), "ab") as f:
            offset = f.tell()
            f.write(data[:half])
            f.flush()
            time.sleep(0.005)
            f.write(data[half:])
            return offset

    monkeypatch.setattr(storage, "append", _slow_append)

    insert_results = []

    def _insert_many():
        for _ in range(100):
            insert_results.append(post_sql(server, "INSERT INTO users VALUES ('kim', 25)"))

    writer = threading.Thread(target=_insert_many)
    writer.start()
    select_results = []
    while writer.is_alive():
        select_results.append(post_sql(server, "SELECT * FROM users"))
    writer.join()

    assert all(status == 201 for status, _ in insert_results)
    assert select_results
    previous = 0
    for status, body in select_results:
        assert status == 200
        for row in body["rows"]:
            assert len(row) == 3
            assert [type(v) for v in row] == [int, str, int]
        assert body["row_count"] >= previous
        previous = body["row_count"]
