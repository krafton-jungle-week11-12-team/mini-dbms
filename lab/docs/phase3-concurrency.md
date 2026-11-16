# Phase 3 체험: 서버의 스레드와 동시성 이슈 (터미널 A + B)

> 선행 조건: [lab/README.md](../README.md)의 "0. Docker 환경 준비"와 [Phase 2 체험의 2-1](phase2-bplustree.md#2-1-100만-건-만들기-workphase2setupsql)(100만 건 `users` 테이블)을 마쳐야 해요.

0.5초짜리 요청 20건을 스레드 10개로 보내면 10.2초가 1.07초로 줄고, 잠금 없이 동시에 잔액을 올리면 200원이 되어야 할 값이 110원이 돼요. lab 컨테이너가 "여러 클라이언트", mysql 컨테이너가 "멀티스레드 서버" 역할을 해요.

## 3-1. MySQL 서버의 스레드 모델 보기 (터미널 B)

```bash
mysql -ujungle -pjungle1234 -t minidb -e "
SHOW VARIABLES WHERE Variable_name IN ('thread_handling','max_connections','thread_cache_size');
SHOW GLOBAL STATUS LIKE 'Threads_%';"
```

| 변수 | 값 | 뜻 |
| --- | --- | --- |
| `thread_handling` | `one-thread-per-connection` | 클라이언트 연결 하나에 스레드 하나를 붙임 |
| `max_connections` | 151 | 동시에 받을 수 있는 연결 상한 |
| `thread_cache_size` | 9 | 끝난 스레드를 버리지 않고 보관해 재사용하는 개수 |

MySQL Community는 연결당 스레드 + 스레드 캐시를 쓰고, 고정 크기 Thread Pool은 Enterprise 판에 플러그인으로 있어요. 우리 구현은 "스레드를 미리 N개 만들어 두고 작업 큐에서 꺼내 쓰는" Thread Pool이므로, 이 차이를 설명할 수 있으면 좋아요.

## 3-2. 동시 요청 + 동시성 이슈 스크립트 (`work/phase3/concurrency.py`)

접속 주소는 compose가 넣어준 `DB_HOST`(= `mysql`)에서 읽어요.

```python
"""Phase 3 체험: 여러 클라이언트가 동시에 DB 서버에 요청하면 어떻게 되는가?"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
import pymysql

CONF = dict(host=os.environ.get("DB_HOST", "127.0.0.1"), user="jungle", password="jungle1234", database="minidb")
N_REQUESTS = 20


def query(i):
    # 요청 1건 = 연결 1개. 서버는 이 연결을 스레드 하나에 붙여 처리한다.
    conn = pymysql.connect(**CONF)
    with conn.cursor() as cur:
        cur.execute("SELECT SLEEP(0.5), name FROM users WHERE id = %s", (i + 1,))
        row = cur.fetchone()
    conn.close()
    return row[1]


def run(workers):
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(query, range(N_REQUESTS)))
    return time.perf_counter() - start


def show_threads(label):
    conn = pymysql.connect(**CONF)
    with conn.cursor() as cur:
        cur.execute("SHOW GLOBAL STATUS LIKE 'Threads_%'")
        print(f"  [{label}]", dict(cur.fetchall()))
    conn.close()


print("1) 요청 20건(각 0.5초 걸림)을 순차 vs 병렬로 보내기")
print(f"  순차(스레드 1개) : {run(1):.2f}s")
print(f"  병렬(스레드 10개): {run(10):.2f}s")
show_threads("서버 스레드 상태")

print("\n2) 동시성 이슈: 잔액 100원에서 10개 스레드가 동시에 +10원씩")
setup = pymysql.connect(**CONF, autocommit=True)
with setup.cursor() as cur:
    cur.execute("DROP TABLE IF EXISTS account")
    cur.execute("CREATE TABLE account (id INT PRIMARY KEY, balance INT)")
    cur.execute("INSERT INTO account VALUES (1, 100)")


def unsafe_deposit(_):
    # 읽고 -> 계산하고 -> 쓰기: 사이에 다른 스레드가 끼어들 수 있다 (lost update)
    conn = pymysql.connect(**CONF, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SELECT balance FROM account WHERE id = 1")
        balance = cur.fetchone()[0]
        time.sleep(0.05)
        cur.execute("UPDATE account SET balance = %s WHERE id = 1", (balance + 10,))
    conn.close()


def safe_deposit(_):
    # 트랜잭션 + SELECT ... FOR UPDATE 로 행 잠금 -> 한 번에 한 스레드만 수정
    conn = pymysql.connect(**CONF)
    with conn.cursor() as cur:
        conn.begin()
        cur.execute("SELECT balance FROM account WHERE id = 1 FOR UPDATE")
        balance = cur.fetchone()[0]
        time.sleep(0.05)
        cur.execute("UPDATE account SET balance = %s WHERE id = 1", (balance + 10,))
        conn.commit()
    conn.close()


for name, fn in [("잠금 없음", unsafe_deposit), ("FOR UPDATE", safe_deposit)]:
    with setup.cursor() as cur:
        cur.execute("UPDATE account SET balance = 100 WHERE id = 1")
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(fn, range(10)))
    with setup.cursor() as cur:
        cur.execute("SELECT balance FROM account WHERE id = 1")
        print(f"  {name:10s}: 기대값 200, 실제 {cur.fetchone()[0]}")
setup.close()
```

```bash
# 터미널 A: docker compose exec lab bash
python /work/phase3/concurrency.py
```

실제 출력:

```text
1) 요청 20건(각 0.5초 걸림)을 순차 vs 병렬로 보내기
  순차(스레드 1개) : 10.20s
  병렬(스레드 10개): 1.07s
  [서버 스레드 상태] {'Threads_cached': '8', 'Threads_connected': '1', 'Threads_created': '10', 'Threads_running': '2'}

2) 동시성 이슈: 잔액 100원에서 10개 스레드가 동시에 +10원씩
  잠금 없음     : 기대값 200, 실제 110
  FOR UPDATE: 기대값 200, 실제 200
```

## 3-3. 서버 쪽에서 지켜보기 (터미널 B)

터미널 A에서 스크립트가 도는 동안 터미널 B에서 실행하면, `State`가 `User sleep`인 연결(=서버 스레드)이 최대 10개 동시에 보여요.

```bash
mysql -ujungle -pjungle1234 -e "SHOW PROCESSLIST;"
```

## 3-4. 결과 읽기

- **병렬 처리**: 서버가 연결마다 스레드를 따로 돌리므로 20건이 10개씩 동시에 처리돼 약 1초에 끝났어요.
- **스레드 재사용**: 연결이 40번 있었는데 `Threads_created`는 10이고 `Threads_cached`는 8이에요. 스레드를 매번 만들지 않고 재사용했다는 뜻으로, Thread Pool을 쓰는 이유와 같아요. (서버를 오래 켜 두었다면 숫자가 더 클 수 있어요.)
- **lost update**: 10개 스레드가 모두 100을 읽고 110을 써서 9번의 입금이 사라졌어요. `FOR UPDATE` 행 잠금을 걸면 순서대로 처리되어 200이 돼요.

---

이전: [Phase 2 체험](phase2-bplustree.md) · 처음으로: [lab/README.md](../README.md)
