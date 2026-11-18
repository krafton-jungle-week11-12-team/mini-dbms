import threading
import time

import pytest

from mini_dbms.executor import Executor
from mini_dbms.nodes import Condition, InsertStmt, SelectStmt
from mini_dbms.storage import Storage

ALL = ["id", "name", "age"]


@pytest.mark.parametrize(
    "prep, ast, expected, expected_file",
    [
        pytest.param(
            "1,kim,23\n",
            SelectStmt(table="users", columns=None, where=None),
            {"columns": ALL, "rows": [[1, "kim", 23]], "affected": 1},
            None,
            id="T-EXE-03 SELECT *",
        ),
        pytest.param(
            "1,kim,23\n2,lee,30\n",
            SelectStmt(table="users", columns=None, where=Condition("age", "=", 23)),
            {"rows": [[1, "kim", 23]], "affected": 1},
            None,
            id="T-EXE-04 WHERE 일치",
        ),
        pytest.param(
            "1,kim,23\n2,lee,30\n",
            SelectStmt(table="users", columns=None, where=Condition("age", ">=", 25)),
            {"rows": [[2, "lee", 30]], "affected": 1},
            None,
            id="T-EXE-05 WHERE 비교 연산자",
        ),
        pytest.param(
            "1,kim,23\n2,lee,30\n",
            SelectStmt(table="users", columns=None, where=Condition("name", "!=", "kim")),
            {"rows": [[2, "lee", 30]], "affected": 1},
            None,
            id="T-EXE-06 WHERE 문자열",
        ),
        pytest.param(
            "1,kim,23\n",
            SelectStmt(table="users", columns=None, where=Condition("age", ">", 100)),
            {"columns": ALL, "rows": [], "affected": 0},
            None,
            id="T-EXE-07 WHERE 일치 없음",
        ),
        pytest.param(
            "1,kim,23\n",
            SelectStmt(table="users", columns=["age", "name"], where=None),
            {"columns": ["age", "name"], "rows": [[23, "kim"]], "affected": 1},
            None,
            id="T-EXE-08 컬럼 순서 바꿔 조회",
        ),
        pytest.param(
            "",
            SelectStmt(table="users", columns=None, where=None),
            {"columns": ALL, "rows": [], "affected": 0},
            None,
            id="T-EXE-09 빈 테이블 조회",
        ),
        pytest.param(
            "2,lee,30\n1,kim,23\n",
            SelectStmt(table="users", columns=None, where=None),
            {"rows": [[2, "lee", 30], [1, "kim", 23]]},
            None,
            id="T-EXE-10 행 순서 (파일 순서 그대로)",
        ),
    ],
)
def test_run(tmp_path, schema, write_csv, prep, ast, expected, expected_file):
    csv_path = write_csv(prep)
    executor = Executor(Storage(tmp_path, schema), schema)

    result = executor.run(ast)

    for field, value in expected.items():
        assert getattr(result, field) == value, field
    if expected_file is not None:
        assert csv_path.read_bytes().decode("utf-8") == expected_file


# ---------------------------------------------------------------------------
# Phase 2: id 자동 부여, 인덱스 복구, 인덱스 조회
# Phase 2에서는 실행기가 id를 부여하므로 InsertStmt.values에는 name, age만 넣어요.
# ---------------------------------------------------------------------------

SELECT_ALL = SelectStmt(table="users", columns=None, where=None)


@pytest.mark.parametrize(
    "prep, inserts, expected_rows, expected_file",
    [
        pytest.param(
            "",
            [["kim", 23], ["lee", 30]],
            [[1, "kim", 23], [2, "lee", 30]],
            None,
            id="T-EXE-11 id 자동 부여",
        ),
        pytest.param(
            "1,kim,23\n",
            [["lee", 30]],
            [[1, "kim", 23], [2, "lee", 30]],
            None,
            id="T-EXE-12 재시작 후 next_id 복구",
        ),
        pytest.param(
            "5,kim,23\n2,lee,30\n",
            [["park", 40]],
            None,
            "5,kim,23\n2,lee,30\n6,park,40\n",
            id="T-EXE-13 마지막 행이 최대 id가 아님",
        ),
    ],
)
def test_auto_id(tmp_path, schema, write_csv, prep, inserts, expected_rows, expected_file):
    csv_path = write_csv(prep)
    executor = Executor(Storage(tmp_path, schema), schema)

    for values in inserts:
        executor.run(InsertStmt(table="users", values=values))

    if expected_rows is not None:
        assert executor.run(SELECT_ALL).rows == expected_rows
    if expected_file is not None:
        assert csv_path.read_bytes().decode("utf-8") == expected_file


@pytest.mark.parametrize(
    "prep, key, expected",
    [
        pytest.param(
            "1,kim,23\n2,lee,30\n",
            2,
            9,
            id="T-EXE-14 인덱스 트리 복구",
        ),
    ],
)
def test_index_recovery(tmp_path, schema, write_csv, prep, key, expected):
    write_csv(prep)
    executor = Executor(Storage(tmp_path, schema), schema)

    assert executor.indexes["users"].search(key) == expected


@pytest.mark.parametrize(
    "prep, ast, expected",
    [
        pytest.param(
            "1,kim,23\n2,lee,30\n",
            SelectStmt(table="users", columns=None, where=Condition("id", "=", 2)),
            {"rows": [[2, "lee", 30]], "affected": 1},
            id="T-EXE-15 인덱스로 한 행 조회",
        ),
        pytest.param(
            "1,kim,23\n",
            SelectStmt(table="users", columns=None, where=Condition("id", "=", 99)),
            {"rows": [], "affected": 0},
            id="T-EXE-16 인덱스에 없는 id",
        ),
    ],
)
def test_select_by_index(tmp_path, schema, write_csv, monkeypatch, prep, ast, expected):
    write_csv(prep)
    storage = Storage(tmp_path, schema)
    executor = Executor(storage, schema)

    # 인덱스 복구가 끝난 뒤에 scan을 막아요. 선형 탐색으로 빠지면 실패해요.
    def fail_scan(*args, **kwargs):
        raise AssertionError("WHERE id = ? 인데 storage.scan이 호출됐어요")

    monkeypatch.setattr(storage, "scan", fail_scan)

    result = executor.run(ast)

    for field, value in expected.items():
        assert getattr(result, field) == value, field


# ---------------------------------------------------------------------------
# Phase 3: Result에 type, inserted_id, used_index 추가
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prep, ast, expected",
    [
        pytest.param(
            "",
            InsertStmt(table="users", values=["kim", 25]),
            {"type": "insert", "inserted_id": 1, "affected": 1},
            id="T-EXE-17 INSERT 결과에 type, inserted_id",
        ),
        pytest.param(
            "1,kim,25\n2,lee,30\n3,park,27\n",
            SelectStmt(table="users", columns=None, where=Condition("id", "=", 2)),
            {"type": "select", "used_index": True, "index_column": "id", "affected": 1},
            id="T-EXE-18 인덱스 조회 시 used_index 참",
        ),
        pytest.param(
            "1,kim,25\n2,lee,30\n3,park,27\n",
            SelectStmt(table="users", columns=None, where=Condition("age", ">", 20)),
            {"type": "select", "used_index": False, "index_column": None},
            id="T-EXE-19 선형 탐색 시 used_index 거짓",
        ),
    ],
)
def test_result_fields(tmp_path, schema, write_csv, prep, ast, expected):
    write_csv(prep)
    executor = Executor(Storage(tmp_path, schema), schema)

    result = executor.run(ast)

    for field, value in expected.items():
        assert getattr(result, field) == value, field


# ---------------------------------------------------------------------------
# Phase 4: 테이블 락
# ---------------------------------------------------------------------------

INSERT_KIM = InsertStmt(table="users", values=["kim", 25])


def run_in_threads(targets, timeout=5):
    """함수들을 스레드에서 동시에 시작하고, 모두 끝날 때까지 기다려요."""
    barrier = threading.Barrier(len(targets))

    def _wrap(target):
        def _run():
            barrier.wait()
            target()
        return _run

    threads = [threading.Thread(target=_wrap(t), daemon=True) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
    assert not any(t.is_alive() for t in threads), "스레드가 시간 안에 끝나지 않았어요"


def test_insert_not_interleaved(tmp_path, schema, write_csv, monkeypatch):
    """T-LK-03 한 명령어를 실행하는 동안 다른 명령어가 끼어들지 못한다

    append() 뒤에 쉬어서 id 발급과 next_id 증가 사이에 끼어들 틈을 만들어요.
    락이 없으면 두 스레드가 모두 id 1을 받아요.
    """
    write_csv("")
    storage = Storage(tmp_path, schema)
    executor = Executor(storage, schema)
    original_append = storage.append

    def _slow_append(table, record):
        offset = original_append(table, record)
        time.sleep(0.05)
        return offset

    monkeypatch.setattr(storage, "append", _slow_append)
    results = []

    run_in_threads([
        lambda: results.append(executor.run(INSERT_KIM)),
        lambda: results.append(executor.run(INSERT_KIM)),
    ])

    assert sorted(r.inserted_id for r in results) == [1, 2]
    assert len((tmp_path / "users.csv").read_text().splitlines()) == 2
    assert executor.indexes["users"].search(1) is not None
    assert executor.indexes["users"].search(2) is not None


def test_one_worker_per_table(tmp_path, schema, write_csv, monkeypatch):
    """T-LK-04 한 테이블에서 워커가 실행하는 동안 다른 워커는 그 테이블에서 실행하지 못한다

    INSERT와 SELECT를 섞어서, 둘이 같은 락을 쓰는지도 같이 확인해요.
    락이 없으면 최댓값이 4예요.
    """
    write_csv("1,kim,25\n")
    executor = Executor(Storage(tmp_path, schema), schema)
    counter_lock = threading.Lock()
    state = {"running": 0, "max": 0}

    def _counted(method):
        def _run(ast):
            with counter_lock:
                state["running"] += 1
                state["max"] = max(state["max"], state["running"])
            try:
                time.sleep(0.05)
                return method(ast)
            finally:
                with counter_lock:
                    state["running"] -= 1
        return _run

    monkeypatch.setattr(executor, "run_insert", _counted(executor.run_insert))
    monkeypatch.setattr(executor, "run_select", _counted(executor.run_select))
    select_all = SelectStmt(table="users", columns=None, where=None)

    run_in_threads([
        lambda: executor.run(INSERT_KIM),
        lambda: executor.run(select_all),
        lambda: executor.run(INSERT_KIM),
        lambda: executor.run(select_all),
    ])

    assert state["max"] == 1


def test_lock_released_after_exception(tmp_path, schema, write_csv, monkeypatch):
    """T-LK-05 실행 중 예외가 나도 락이 풀린다

    락을 놓지 않으면 두 번째 호출이 멈추므로, 별도 스레드에서 실행하고 1초만 기다려요.
    """
    write_csv("")
    storage = Storage(tmp_path, schema)
    executor = Executor(storage, schema)
    original_append = storage.append
    calls = []

    def _fail_once(table, record):
        calls.append(record)
        if len(calls) == 1:
            raise OSError("디스크 쓰기 실패")
        return original_append(table, record)

    monkeypatch.setattr(storage, "append", _fail_once)

    with pytest.raises(OSError):
        executor.run(INSERT_KIM)

    results = []
    second = threading.Thread(
        target=lambda: results.append(executor.run(INSERT_KIM)), daemon=True
    )
    second.start()
    second.join(timeout=1)

    assert not second.is_alive(), "두 번째 INSERT가 락을 기다리며 멈췄어요"
    assert results[0].affected == 1


# ---------------------------------------------------------------------------
# 보조 인덱스: messages.client_id (중복 허용)
# ---------------------------------------------------------------------------

MSG_SCHEMA = {
    "messages": [("id", "INT"), ("author", "TEXT"), ("client_id", "TEXT")],
}
MSG_SECONDARY = {"messages": ["client_id"]}


def _msg_executor(tmp_path):
    return Executor(
        Storage(tmp_path, MSG_SCHEMA), MSG_SCHEMA, secondary_indexes=MSG_SECONDARY,
    )


def _insert_msgs(executor, pairs):
    for author, client_id in pairs:
        executor.run(InsertStmt(table="messages", values=[author, client_id]))


def _by_client(client_id, op="="):
    return SelectStmt(
        table="messages", columns=None, where=Condition("client_id", op, client_id),
    )


SAMPLE = [("minji", "aaa"), ("seojun", "bbb"), ("minji", "aaa"), ("hayun", "ccc"), ("minji", "aaa")]


def test_secondary_returns_all_duplicates_in_order(tmp_path, write_csv):
    """T-SEC-01 같은 client_id의 행을 모두, 삽입 순서대로 돌려준다"""
    write_csv("", table="messages")
    executor = _msg_executor(tmp_path)
    _insert_msgs(executor, SAMPLE)

    result = executor.run(_by_client("aaa"))

    assert result.used_index is True
    assert result.index_column == "client_id"
    assert result.rows == [[1, "minji", "aaa"], [3, "minji", "aaa"], [5, "minji", "aaa"]]


def test_secondary_missing_key(tmp_path, write_csv):
    """T-SEC-02 없는 client_id는 빈 결과"""
    write_csv("", table="messages")
    executor = _msg_executor(tmp_path)
    _insert_msgs(executor, SAMPLE)

    result = executor.run(_by_client("zzz"))

    assert result.used_index is True
    assert result.rows == []


def test_secondary_rebuilt_on_load(tmp_path, write_csv):
    """T-SEC-03 다시 띄워도(_load) 보조 인덱스 결과가 같다"""
    write_csv("", table="messages")
    _insert_msgs(_msg_executor(tmp_path), SAMPLE)

    reloaded = _msg_executor(tmp_path)

    assert reloaded.run(_by_client("aaa")).rows == [
        [1, "minji", "aaa"], [3, "minji", "aaa"], [5, "minji", "aaa"],
    ]
    assert reloaded.run(_by_client("ccc")).rows == [[4, "hayun", "ccc"]]


def test_secondary_matches_full_scan(tmp_path, write_csv):
    """T-SEC-04 보조 인덱스 결과가 선형 탐색 결과와 같다"""
    write_csv("", table="messages")
    indexed = _msg_executor(tmp_path)
    _insert_msgs(indexed, SAMPLE)
    plain = Executor(Storage(tmp_path, MSG_SCHEMA), MSG_SCHEMA)

    for client_id in ["aaa", "bbb", "ccc", "zzz"]:
        with_index = indexed.run(_by_client(client_id))
        without = plain.run(_by_client(client_id))
        assert with_index.used_index and not without.used_index
        assert with_index.rows == without.rows


def test_secondary_not_used_for_other_ops(tmp_path, write_csv):
    """T-SEC-05 = 이 아닌 조건은 선형 탐색"""
    write_csv("", table="messages")
    executor = _msg_executor(tmp_path)
    _insert_msgs(executor, SAMPLE)

    result = executor.run(_by_client("aaa", op="!="))

    assert result.used_index is False
    assert result.index_column is None
    assert [row[0] for row in result.rows] == [2, 4]


def test_id_lookup_still_uses_primary(tmp_path, write_csv):
    """T-SEC-06 보조 인덱스가 있어도 id 조회는 기본 키 트리를 쓴다"""
    write_csv("", table="messages")
    executor = _msg_executor(tmp_path)
    _insert_msgs(executor, SAMPLE)

    result = executor.run(SelectStmt(table="messages", columns=None, where=Condition("id", "=", 4)))

    assert result.used_index is True
    assert result.index_column == "id"
    assert result.rows == [[4, "hayun", "ccc"]]
