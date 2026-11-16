import pytest

from mini_dbms.cli import main, split_statements


@pytest.mark.parametrize(
    "sql, expected",
    [
        pytest.param(
            "INSERT INTO memo VALUES (1, 'a'); SELECT * FROM memo;",
            ["INSERT INTO memo VALUES (1, 'a')", " SELECT * FROM memo"],
            id="T-CLI-01 명령어 분리",
        ),
        pytest.param(
            "INSERT INTO memo VALUES (1, 'a');;",
            ["INSERT INTO memo VALUES (1, 'a')", ""],
            id="T-CLI-02 빈 명령어도 결과에 포함",
        ),
        pytest.param(
            "INSERT INTO memo VALUES (1, 'a);",
            ["INSERT INTO memo VALUES (1, 'a);"],
            id="T-CLI-03 닫히지 않은 따옴표도 그대로",
        ),
    ],
)
def test_split_statements(sql, expected):
    assert split_statements(sql) == expected


def _run_main(argv):
    """main()이 종료 코드를 반환하든 sys.exit()을 하든 종료 코드를 돌려줘요."""
    try:
        return main(argv)
    except SystemExit as e:
        return e.code


@pytest.mark.parametrize(
    "make_argv",
    [
        pytest.param(lambda tmp: [], id="T-CLI-04 인자 없음"),
        pytest.param(lambda tmp: ["a.sql", "b.sql"], id="T-CLI-05 인자 2개"),
        pytest.param(lambda tmp: [str(tmp / "nofile.sql")], id="T-CLI-06 파일 없음"),
        pytest.param(
            lambda tmp: [str(_write(tmp / "blank.sql", "  \n\t\n"))],
            id="T-CLI-07 빈 파일",
        ),
    ],
)
def test_cli_error(tmp_path, make_argv):
    assert _run_main(make_argv(tmp_path)) == 1


def _write(path, content):
    path.write_text(content, encoding="utf-8")
    return path
