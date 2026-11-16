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
