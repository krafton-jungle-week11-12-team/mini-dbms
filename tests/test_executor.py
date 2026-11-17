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

