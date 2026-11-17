"""id 조회(B+ 트리)와 name 조회(선형 탐색)의 속도를 비교해요.

    python scripts/gen_data.py --rows 1000000
    python scripts/bench.py --repeat 5

엔진은 한 번만 만들어서, 기동 시 인덱스 재구축 시간이 조회 시간에 섞이지 않게 해요.
조회는 실제 SQL 문장을 engine.execute()에 넘겨서 Phase 1 처리기 전체를 거쳐요.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mini_dbms.engine import Engine  # noqa: E402


def timed(engine: Engine, sql: str, repeat: int):
    times, result = [], None
    for _ in range(repeat):
        start = time.perf_counter()
        result = engine.execute(sql)
        times.append((time.perf_counter() - start) * 1000)
    return statistics.mean(times), result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="인덱스 조회 vs 선형 탐색")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--repeat", type=int, default=5, help="조회마다 반복 횟수 (평균을 냄)")
    args = p.parse_args(argv)

    start = time.perf_counter()
    engine = Engine(args.data_dir)
    load_s = time.perf_counter() - start
    total = engine.executor.next_id["users"] - 1
    if total == 0:
        print("데이터가 없어요. 먼저 scripts/gen_data.py를 실행해 주세요.")
        return 1

    targets = [("처음", 1), ("가운데", total // 2), ("끝", total), ("없음", total + 1)]
    print(f"레코드 {total:,}건, 엔진 기동(인덱스 재구축) {load_s:.2f}초, 반복 {args.repeat}회 평균\n")
    print(f"| 위치 | id | id 조회 (ms) | name 조회 (ms) | 배수 |")
    print(f"| --- | ---: | ---: | ---: | ---: |")
    for label, i in targets:
        id_ms, by_id = timed(engine, f"SELECT * FROM users WHERE id = {i}", args.repeat)
        name_ms, by_name = timed(engine, f"SELECT * FROM users WHERE name = 'user{i}'", args.repeat)
        assert by_id.rows == by_name.rows, f"결과가 다름: id={i}"
        ratio = name_ms / id_ms if id_ms else float("inf")
        print(f"| {label} | {i:,} | {id_ms:.3f} | {name_ms:,.1f} | {ratio:,.0f}배 |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
