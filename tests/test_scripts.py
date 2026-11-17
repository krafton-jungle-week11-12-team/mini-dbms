"""대량 데이터 생성과 벤치마크 스크립트가 처리기와 맞물리는지 확인해요."""

import importlib.util
from pathlib import Path

from mini_dbms.engine import Engine

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_csv_mode_is_read_back_with_index(tmp_path):
    load("gen_data").write_csv(tmp_path, 1000, seed=1)
    engine = Engine(tmp_path)
    assert engine.executor.next_id["users"] == 1001
    by_id = engine.execute("SELECT * FROM users WHERE id = 777").rows
    by_name = engine.execute("SELECT * FROM users WHERE name = 'user777'").rows
    assert by_id == by_name and by_id[0][:2] == [777, "user777"]


def test_engine_mode_assigns_ids(tmp_path):
    load("gen_data").insert_with_engine(tmp_path, 50, seed=1)
    engine = Engine(tmp_path)
    assert engine.executor.next_id["users"] == 51
    assert engine.execute("SELECT name FROM users WHERE id = 50").rows == [["user50"]]


def test_csv_and_engine_modes_write_same_file(tmp_path):
    gen = load("gen_data")
    gen.write_csv(tmp_path / "a", 30, seed=7)
    gen.insert_with_engine(tmp_path / "b", 30, seed=7)
    assert (tmp_path / "a" / "users.csv").read_bytes() == (tmp_path / "b" / "users.csv").read_bytes()


def test_sql_mode_runs_through_cli(tmp_path, monkeypatch):
    load("gen_data").write_sql(tmp_path / "bulk.sql", 20, seed=1)
    monkeypatch.setenv("MINI_DBMS_DATA", str(tmp_path / "data"))
    from mini_dbms.cli import main
    assert main([str(tmp_path / "bulk.sql")]) == 0
    assert Engine(tmp_path / "data").executor.next_id["users"] == 21


def test_bench_runs(tmp_path, capsys):
    load("gen_data").write_csv(tmp_path, 500, seed=1)
    assert load("bench").main(["--data-dir", str(tmp_path), "--repeat", "1"]) == 0
    assert "id 조회" in capsys.readouterr().out
