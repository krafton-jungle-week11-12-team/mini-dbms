import pytest

from mini_dbms.storage import Storage


def _append_then_scan(storage):
    storage.append("users", [1, "a,b", 23])
    return list(storage.scan("users"))


@pytest.mark.parametrize(
    "prep, action, expected, expected_file",
    [
        pytest.param(
            "",
            lambda s: s.append("users", [1, "kim", 23]),
            0,
            "1,kim,23\n",
            id="T-STO-01 빈 파일에 추가",
        ),
        pytest.param(
            "1,kim,23\n",
            lambda s: s.append("users", [2, "lee", 30]),
            9,
            None,
            id="T-STO-02 이어서 추가 (앞 행의 바이트 수)",
        ),
        pytest.param(
            "1,김,23\n",
            lambda s: s.append("users", [2, "lee", 30]),
            9,
            None,
            id="T-STO-03 한글 값의 오프셋 (김은 3바이트)",
        ),
        pytest.param(
            "",
            _append_then_scan,
            [(0, [1, "a,b", 23])],
            None,
            id="T-STO-04 쉼표가 든 값",
        ),
        pytest.param(
            "1,kim,23\n2,lee,30\n",
            lambda s: list(s.scan("users")),
            [(0, [1, "kim", 23]), (9, [2, "lee", 30])],
            None,
            id="T-STO-05 전체 읽기",
        ),
        pytest.param(
            "",
            lambda s: list(s.scan("users")),
            [],
            None,
            id="T-STO-06 빈 파일 읽기",
        ),
        pytest.param(
            "1,kim,23\n2,lee,30\n",
            lambda s: s.read_at("users", 9),
            [2, "lee", 30],
            None,
            id="T-STO-07 위치로 한 행 읽기",
        ),
        pytest.param(
            "1,kim,23\n",
            lambda s: list(s.scan("users")),
            [(0, [1, "kim", 23])],  # 23 == "23"은 False라서 타입까지 확인돼요
            None,
            id="T-STO-08 숫자 타입 복원",
        ),
    ],
)
def test_storage(tmp_path, schema, write_csv, prep, action, expected, expected_file):
    csv_path = write_csv(prep)
    storage = Storage(tmp_path, schema)

    result = action(storage)

    assert result == expected
    if expected_file is not None:
        assert csv_path.read_bytes().decode("utf-8") == expected_file
