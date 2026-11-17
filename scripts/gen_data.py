"""대량 레코드를 만들어요.

    python scripts/gen_data.py --rows 1000000              # CSV에 바로 쓰기 (빠름)
    python scripts/gen_data.py --rows 10000 --mode engine  # SQL 처리기로 INSERT (느림, 실제 경로)
    python scripts/gen_data.py --rows 1000 --mode sql      # CLI로 돌릴 SQL 파일 만들기

name은 user<id>로 고유하게 만들어서, id 조회와 name 조회가 같은 행을 찾게 해요.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mini_dbms.engine import Engine  # noqa: E402


def record(i: int, rng: random.Random) -> list:
    return [i, f"user{i}", rng.randint(10, 79)]


def write_csv(data_dir: Path, rows: int, seed: int) -> Path:
    """저장 계층과 같은 형식(id,name,age 한 줄)으로 users.csv를 새로 써요."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "users.csv"
    rng = random.Random(seed)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        for i in range(1, rows + 1):
            writer.writerow(record(i, rng))
    return path


def insert_with_engine(data_dir: Path, rows: int, seed: int) -> None:
    """SQL 처리기를 그대로 거쳐 INSERT해요. id는 실행기가 붙여요."""
    path = data_dir / "users.csv"
    if path.exists():
        path.unlink()
    engine = Engine(data_dir)
    rng = random.Random(seed)
    for i in range(1, rows + 1):
        _, name, age = record(i, rng)
        engine.execute(f"INSERT INTO users VALUES ('{name}', {age})")


def write_sql(out: Path, rows: int, seed: int) -> None:
    """./mini-dbms 로 실행할 SQL 파일을 만들어요."""
    rng = random.Random(seed)
    with open(out, "w", encoding="utf-8") as f:
        for i in range(1, rows + 1):
            _, name, age = record(i, rng)
            f.write(f"INSERT INTO users VALUES ('{name}', {age});\n")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="대량 레코드 생성")
    p.add_argument("--rows", type=int, default=1_000_000)
    p.add_argument("--mode", choices=["csv", "engine", "sql"], default="csv")
    p.add_argument("--data-dir", default="data", help="csv, engine 모드에서 쓸 폴더")
    p.add_argument("--out", default="bulk.sql", help="sql 모드에서 만들 파일")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)

    start = time.perf_counter()
    if args.mode == "csv":
        path = write_csv(Path(args.data_dir), args.rows, args.seed)
        where = path
    elif args.mode == "engine":
        insert_with_engine(Path(args.data_dir), args.rows, args.seed)
        where = Path(args.data_dir) / "users.csv"
    else:
        write_sql(Path(args.out), args.rows, args.seed)
        where = Path(args.out)
    took = time.perf_counter() - start
    print(f"{args.rows:,}건 생성 ({args.mode}) → {where} [{took:.2f}초]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
