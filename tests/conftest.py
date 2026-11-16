import pytest

# 스키마: users(id INT, name TEXT, age INT)
SCHEMA = {
    "users": [("id", "INT"), ("name", "TEXT"), ("age", "INT")],
}


@pytest.fixture
def schema():
    return SCHEMA


@pytest.fixture
def write_csv(tmp_path):
    """tmp_path에 users.csv를 머리글 없이 데이터만 써요."""

    def _write(content, table="users"):
        path = tmp_path / f"{table}.csv"
        path.write_bytes(content.encode("utf-8"))
        return path

    return _write
