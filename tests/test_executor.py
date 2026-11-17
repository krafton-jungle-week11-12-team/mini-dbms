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
            {"type": "select", "used_index": True, "affected": 1},
            id="T-EXE-18 인덱스 조회 시 used_index 참",
        ),
        pytest.param(
            "1,kim,25\n2,lee,30\n3,park,27\n",
            SelectStmt(table="users", columns=None, where=Condition("age", ">", 20)),
            {"type": "select", "used_index": False},
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
