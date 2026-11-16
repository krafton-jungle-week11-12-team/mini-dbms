# 미니 DBMS 체험 튜토리얼: Docker로 설치부터 실행까지

## 개요

Docker Desktop만 있으면 `docker compose up` 한 번으로 SQLite·MySQL·Python 실습 환경이 떠요. 그러면 과제의 Phase 1~3을 OS와 상관없이 같은 명령으로 체험할 수 있어요. 컨테이너는 두 개만 써요.

- `mini-lab`: Python 3.12 + SQLite + pymysql. Phase 1(SQLite)과 Phase 3(동시 요청 클라이언트)을 실행하는 작업대
- `mini-mysql`: MySQL 8.0 서버. Phase 2(B+ 트리)와 Phase 3(멀티스레드 서버)의 대상

내 PC의 `work` 폴더가 두 컨테이너의 `/work`에 공유되므로, SQL 파일은 평소 쓰던 에디터로 고치고 실행은 컨테이너 안에서 해요.

```text
                 ┌──────────────────────────────────┐
                 │ 내 PC · mini-dbms/lab/work       │
                 │ 에디터로 SQL·Python 파일 작성    │
                 └────────────────┬─────────────────┘
                                  │ /work 공유
                 ┌────────────────┴─────────────────┐
                 ▼                                  ▼
┌──────────────────────────────┐    ┌──────────────────────────────────┐
│ mini-lab 컨테이너            │    │ mini-mysql 컨테이너              │
│ Python 3.12 · sqlite3 ·      │───▶│ MySQL 8.0 · DB minidb ·          │
│ pymysql                      │    │ jungle 계정                      │
│ 터미널 A · Phase 1, Phase 3  │    │ 터미널 B · Phase 2, Phase 3 관찰 │
└──────────────────────────────┘    └────────────────┬─────────────────┘
                     mysql:3306                      │ 데이터 저장
                                                     ▼
                                    ┌──────────────────────────────────┐
                                    │ mysql-data 볼륨 (재시작해도 유지) │
                                    └──────────────────────────────────┘
```

lab에서 MySQL에 접속할 때 주소는 `localhost`가 아니라 서비스 이름 `mysql`이에요.

| 과제 단계 | 실행 위치 | 직접 확인할 것 | 우리 구현과의 연결 |
| --- | --- | --- | --- |
| Phase 1. SQL 처리기 | `mini-lab` (SQLite) | `.sql` 파일을 CLI로 넘겨 INSERT/SELECT, 테이블이 파일 1개로 저장됨 | 입력 → 파싱 → 실행 → 저장, 에러 처리 |
| Phase 2. B+ 트리 인덱스 | `mini-mysql` (InnoDB) | 100만 건에서 `WHERE id = ?` vs 다른 컬럼 조회 속도 | 자동 ID + B+ 트리 vs 선형 탐색 |
| Phase 3. API 서버 | `mini-lab` → `mini-mysql` | 동시 요청 병렬 처리, 서버 스레드 재사용, lost update | Thread Pool, 동시성 제어 |

준비물은 [Docker Desktop](https://www.docker.com/products/docker-desktop/)(Windows·macOS) 또는 Docker Engine + Compose 플러그인(Linux)이에요. 이미지와 데이터를 합쳐 약 1.5 GB의 디스크가 필요해요. SQL과 Python 스크립트의 결과는 Ubuntu 24.04 + SQLite 3.45 + MySQL 8.0.46에서 실제로 실행한 값이에요.

## 0. Docker 환경 준비

팀 저장소의 `lab/` 폴더에 이 문서의 파일이 모두 들어 있어서, 클론하고 `docker compose up -d --build` 한 번이면 끝나요. 파일을 직접 만들 필요는 없고, 0-1과 0-2는 구성을 이해하기 위한 설명이에요.

```bash
git clone https://github.com/krafton-jungle-week11-12-team/mini-dbms.git
cd mini-dbms/lab
```

### 0-1. 폴더 구조

```text
mini-dbms/lab/
├── Dockerfile          # mini-lab 이미지 (Python + SQLite + pymysql)
├── compose.yaml        # mysql + lab 두 컨테이너 정의
└── work/               # 두 컨테이너의 /work 와 공유됨
    ├── phase1/  schema.sql  insert.sql  select.sql
    ├── phase2/  setup.sql  compare.sql  index.sql
    └── phase3/  concurrency.py
```

### 0-2. `Dockerfile`과 `compose.yaml`

`Dockerfile`

```dockerfile
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends sqlite3 file binutils \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pymysql
WORKDIR /work
CMD ["sleep", "infinity"]
```

`compose.yaml`

```yaml
services:
  mysql:
    image: mysql:8.0
    container_name: mini-mysql
    environment:
      MYSQL_ROOT_PASSWORD: root1234
      MYSQL_DATABASE: minidb
      MYSQL_USER: jungle
      MYSQL_PASSWORD: jungle1234
    volumes:
      - ./work:/work
      - mysql-data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-uroot", "-proot1234"]
      interval: 5s
      timeout: 3s
      retries: 30

  lab:
    build: .
    container_name: mini-lab
    working_dir: /work
    volumes:
      - ./work:/work
    environment:
      DB_HOST: mysql
    depends_on:
      mysql:
        condition: service_healthy

volumes:
  mysql-data:
```

포인트 세 가지:

- `MYSQL_*` 환경변수로 최초 실행 때 `minidb` DB와 `jungle` 계정이 자동으로 만들어져요.
- `healthcheck` + `condition: service_healthy` 덕분에 MySQL이 접속 가능해진 뒤에 lab이 떠요.
- lab에서 MySQL 주소는 `localhost`가 아니라 서비스 이름 `mysql`이에요(`DB_HOST`). 포트를 내 PC에 열지 않으므로 로컬에 MySQL이 있어도 충돌하지 않아요.

### 0-3. 실행과 확인

```bash
cd mini-dbms/lab
docker compose up -d --build   # 처음에는 이미지 다운로드로 1~3분
docker compose ps              # mini-mysql 이 (healthy), mini-lab 이 Up 이면 성공
```

이 문서의 이전 버전대로 `docker run --name mini-mysql ...`을 실행한 적이 있다면, `up` 전에 `docker rm -f mini-mysql`로 예전 컨테이너를 먼저 지워 주세요. 그렇지 않으면 이름 충돌(`Conflict`) 에러가 나요.

이후 실습은 두 컨테이너 안에 들어가서 해요. 터미널 창을 두 개 열어 두면 편해요.

| 터미널 | 들어가는 명령 | 프롬프트 | 쓰는 단계 |
| --- | --- | --- | --- |
| A (lab) | `docker compose exec lab bash` | `root@...:/work#` | Phase 1, Phase 3 |
| B (mysql) | `docker compose exec mysql bash` | `bash-5.1#` | Phase 2, Phase 3 관찰 |

컨테이너 안에서 명령을 치기 때문에 Windows PowerShell의 `<` 리다이렉션 문제도 생기지 않아요. 나올 때는 `exit`.

## 1. Phase 1 체험: 텍스트 SQL → CLI → 파일 저장 (터미널 A: lab)

SQLite는 "`.sql` 파일을 커맨드라인으로 넘기면 파싱·실행하고 파일 하나에 저장하는" Phase 1 요구사항과 구조가 거의 같아요.

### 1-1. SQL 파일 3개 (`work/phase1/`)

과제는 테이블이 이미 있다고 가정하므로, 스키마는 미리 한 번만 만들어요. 내 PC의 에디터로 만들면 컨테이너에 바로 보여요.

`schema.sql`

```sql
CREATE TABLE users (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  name  TEXT NOT NULL,
  age   INTEGER,
  email TEXT
);
```

`insert.sql`

```sql
INSERT INTO users (name, age, email) VALUES ('kim', 25, 'kim@example.com');
INSERT INTO users (name, age, email) VALUES ('lee', 31, 'lee@example.com');
INSERT INTO users (name, age, email) VALUES ('park', 28, 'park@example.com');
```

`select.sql`

```sql
.headers on
.mode column
SELECT * FROM users;
SELECT name, age FROM users WHERE age > 26;
SELECT * FROM users WHERE id = 2;
```

### 1-2. CLI로 실행하기

```bash
# 터미널 A: docker compose exec lab bash
cd /work/phase1
sqlite3 mini.db < schema.sql
sqlite3 mini.db < insert.sql
sqlite3 mini.db < select.sql
```

실제 출력:

```text
id  name  age  email
--  ----  ---  ----------------
1   kim   25   kim@example.com
2   lee   31   lee@example.com
3   park  28   park@example.com
name  age
----  ---
lee   31
park  28
id  name  age  email
--  ----  ---  ---------------
2   lee   31   lee@example.com
```

id는 지정하지 않았는데 1, 2, 3으로 자동 부여됐어요. Phase 2의 "레코드 추가 시 ID 자동 부여"가 바로 이 동작이에요. 다시 해보려면 `rm mini.db` 후 처음부터 실행하세요.

### 1-3. "테이블 = 파일" 눈으로 확인하기

```bash
ls -l mini.db                    # 12288 bytes = 4KB 페이지 3개
file mini.db                     # SQLite 3.x database, ... database pages 3
strings mini.db | grep example   # 저장된 값이 바이너리 안에 그대로 보인다
```

`mini.db`는 내 PC의 `work/phase1/`에도 생기므로 DB Browser for SQLite 같은 프로그램으로 열어볼 수도 있어요. SQLite는 데이터를 CSV가 아닌 4KB 페이지 단위 바이너리로 저장하고, 우리 팀이 저장 포맷(CSV / binary / custom)을 고를 때 비교 기준이 돼요.

### 1-4. 엣지 케이스 던져보기

| 입력 | SQLite 반응 | 우리 구현에서 정해야 할 것 |
| --- | --- | --- |
| `sqlite3 mini.db "SELEC * FROM users;"` | `syntax error`와 함께 틀린 위치를 `^`로 표시 | 파서 에러 메시지에 위치 포함 여부 |
| `sqlite3 mini.db "SELECT * FROM nope;"` | `no such table: nope` | 없는 테이블(파일) 처리 |
| `sqlite3 mini.db "INSERT INTO users(name, age) VALUES('choi', 'abc');"` | 에러 없이 저장되고, `SELECT typeof(age) FROM users WHERE name='choi';`는 `text` | 타입 검사를 할지 말지 |

## 2. Phase 2 체험: 100만 건에서 B+ 트리 vs 선형 탐색 (터미널 B: mysql)

100만 건에서 `id`로 찾으면 0.24ms, `email`로 찾으면 165ms가 걸려 약 700배 차이가 났어요. MySQL InnoDB는 PRIMARY KEY로 B+ 트리(클러스터드 인덱스)를 만들기 때문에, 과제의 "자동 ID → B+ 트리 등록" 구조와 같아요.

### 2-1. 100만 건 만들기 (`work/phase2/setup.sql`)

대량 데이터를 한 번에 만드는 방법으로 재귀 CTE를 써요. 테스트 환경에서 약 4초 걸렸어요.

```sql
DROP TABLE IF EXISTS users;
CREATE TABLE users (
  id    BIGINT AUTO_INCREMENT PRIMARY KEY,
  name  VARCHAR(30) NOT NULL,
  age   INT NOT NULL,
  email VARCHAR(60) NOT NULL
) ENGINE=InnoDB;

SET SESSION cte_max_recursion_depth = 1000000;
INSERT INTO users (name, age, email)
WITH RECURSIVE seq(n) AS (
  SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 1000000
)
SELECT CONCAT('user', n), 20 + (n % 50), CONCAT('user', n, '@example.com') FROM seq;

SELECT COUNT(*) AS total_rows FROM users;
```

```bash
# 터미널 B: docker compose exec mysql bash
cd /work/phase2
mysql -ujungle -pjungle1234 -t minidb < setup.sql
```

### 2-2. 인덱스 사용 vs 선형 탐색 (`compare.sql`)

```sql
SET profiling = 1;
SELECT * FROM users WHERE id = 777777;                       -- B+ 트리
SELECT * FROM users WHERE email = 'user777777@example.com';  -- 선형 탐색
SHOW PROFILES;
EXPLAIN SELECT * FROM users WHERE id = 777777;
EXPLAIN SELECT * FROM users WHERE email = 'user777777@example.com';
```

```bash
mysql -ujungle -pjungle1234 -t minidb < compare.sql
```

실측 결과 (환경마다 숫자는 다르지만 차이의 크기는 비슷해요):

| 조회 | 실행 시간 | EXPLAIN `type` | `key` | 읽은 행(추정) |
| --- | --- | --- | --- | --- |
| `WHERE id = 777777` | 0.24 ms | `const` | `PRIMARY` | 1 |
| `WHERE email = ...` (인덱스 없음) | 165 ms | `ALL` (풀 스캔) | 없음 | 1,000,000 |
| `WHERE email = ...` (인덱스 추가 후) | 0.31 ms | `ref` | `idx_email` | 1 |

`EXPLAIN`의 `type`이 핵심이에요. `const`는 트리를 따라가 한 행만 집었다는 뜻이고, `ALL`은 100만 행을 처음부터 끝까지 훑었다는 뜻이에요. `EXPLAIN ANALYZE SELECT ...`를 쓰면 `Table scan on users ... rows=1e+6`처럼 실제 스캔 행 수도 볼 수 있어요.

### 2-3. 보조 인덱스를 추가하면? (`index.sql`)

```sql
CREATE INDEX idx_email ON users(email);
SET profiling = 1;
SELECT * FROM users WHERE email = 'user777777@example.com';
SHOW PROFILES;
EXPLAIN SELECT * FROM users WHERE email = 'user777777@example.com';
```

```bash
mysql -ujungle -pjungle1234 -t minidb < index.sql
```

email에도 B+ 트리가 생기면서 표의 세 번째 행처럼 빨라져요. 우리 구현은 id만 인덱싱하지만, "다른 필드에도 인덱스"는 차별화 아이디어가 될 수 있어요. 다시 비교하려면 `mysql -ujungle -pjungle1234 minidb -e "DROP INDEX idx_email ON users;"`로 지우세요.

### 2-4. 파일로 확인하기 (선택)

```bash
ls -lh /var/lib/mysql/minidb/    # 터미널 B (mysql 컨테이너 안)
```

100만 건이 `users.ibd` 파일 하나(약 116 MB)에 들어 있어요. InnoDB는 이 파일 안에 16KB 페이지로 B+ 트리를 저장하고, 과제의 메모리 기반 B+ 트리는 이것을 단순화한 버전이에요. 이 데이터는 Docker 볼륨(`mysql-data`)에 있어서 컨테이너를 끄고 켜도 유지돼요.

## 3. Phase 3 체험: 서버의 스레드와 동시성 이슈 (터미널 A + B)

0.5초짜리 요청 20건을 스레드 10개로 보내면 10.2초가 1.07초로 줄고, 잠금 없이 동시에 잔액을 올리면 200원이 되어야 할 값이 110원이 돼요. lab 컨테이너가 "여러 클라이언트", mysql 컨테이너가 "멀티스레드 서버" 역할을 해요. Phase 2의 `users` 테이블을 쓰므로 2-1을 먼저 실행해 두세요.

### 3-1. MySQL 서버의 스레드 모델 보기 (터미널 B)

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

### 3-2. 동시 요청 + 동시성 이슈 스크립트 (`work/phase3/concurrency.py`)

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

### 3-3. 서버 쪽에서 지켜보기 (터미널 B)

터미널 A에서 스크립트가 도는 동안 터미널 B에서 실행하면, `State`가 `User sleep`인 연결(=서버 스레드)이 최대 10개 동시에 보여요.

```bash
mysql -ujungle -pjungle1234 -e "SHOW PROCESSLIST;"
```

### 3-4. 결과 읽기

- **병렬 처리**: 서버가 연결마다 스레드를 따로 돌리므로 20건이 10개씩 동시에 처리돼 약 1초에 끝났어요.
- **스레드 재사용**: 연결이 40번 있었는데 `Threads_created`는 10이고 `Threads_cached`는 8이에요. 스레드를 매번 만들지 않고 재사용했다는 뜻으로, Thread Pool을 쓰는 이유와 같아요. (서버를 오래 켜 두었다면 숫자가 더 클 수 있어요.)
- **lost update**: 10개 스레드가 모두 100을 읽고 110을 써서 9번의 입금이 사라졌어요. `FOR UPDATE` 행 잠금을 걸면 순서대로 처리되어 200이 돼요.

## 4. 정리

체험에서 확인한 동작을 우리 미니 DBMS의 기능 테스트 기준으로 그대로 쓸 수 있고, 같은 compose 환경에 우리 서버를 서비스로 추가하면 Phase 3 데모 환경으로도 이어져요.

### 우리 구현에 가져갈 체크리스트

- [ ] Phase 1: `./mini-dbms query.sql`처럼 SQL 파일을 받아 INSERT/SELECT 실행, 문법 오류·없는 테이블·타입 오류 메시지 정의
- [ ] Phase 1: 저장 포맷 결정 (CSV는 단순, SQLite처럼 페이지 단위 바이너리는 빠름)
- [ ] Phase 2: INSERT 시 자동 id 부여 → B+ 트리에 (id → 레코드 위치) 등록
- [ ] Phase 2: `WHERE id = ?`일 때만 인덱스 경로, 나머지는 선형 탐색. `EXPLAIN`처럼 어느 경로를 탔는지 출력하면 발표 때 보여주기 좋음
- [ ] Phase 2: 100만 건 생성 스크립트와 속도 비교표 (2-2 표와 같은 형식)
- [ ] Phase 3: 고정 크기 Thread Pool + 작업 큐, 요청별 스레드 할당
- [ ] Phase 3: 동시 INSERT 시 id 중복·B+ 트리 손상을 막는 락 설계, 3-2 스크립트 같은 동시성 테스트
- [ ] Phase 3: 우리 API 서버도 `Dockerfile` + `compose.yaml` 서비스로 만들어 `docker compose up` 한 번으로 데모되게 하기

### 종료·초기화 명령 (`mini-dbms/lab` 폴더에서)

```bash
docker compose stop        # 잠시 멈추기 (데이터 유지)
docker compose start       # 다시 켜기
docker compose down        # 컨테이너 삭제 (MySQL 데이터는 볼륨에 남음)
docker compose down -v     # 컨테이너 + MySQL 데이터까지 완전 초기화
```

SQLite DB는 `work/phase1/mini.db` 파일만 지우면 초기화돼요.

### 트러블슈팅

| 증상 | 해결 |
| --- | --- |
| `Cannot connect to the Docker daemon` | Docker Desktop을 실행하고 고래 아이콘이 Running이 될 때까지 기다린 뒤 다시 실행 |
| `docker compose ps`에서 mysql이 계속 `(health: starting)` | 최초 초기화는 30초~1분 걸림. `docker compose logs mysql`에 `ready for connections`가 나오는지 확인 |
| `MYSQL_*` 값을 바꿨는데 새 계정으로 접속이 안 됨 | 환경변수는 볼륨이 비어 있을 때만 적용됨. `docker compose down -v` 후 다시 `up` |
| lab에서 `Can't connect to MySQL server on '127.0.0.1'` | 컨테이너 안의 127.0.0.1은 자기 자신. 호스트를 `mysql`(서비스 이름)로 지정 |
| `Recursive query aborted after 1001 iterations` | `SET SESSION cte_max_recursion_depth = 1000000;`이 같은 파일 안에서 먼저 실행됐는지 확인 |
| `Using a password on the command line ... insecure` 경고 | 실습용이라 무시해도 됨 |
| Windows에서 `work` 폴더 파일이 컨테이너에 안 보임 | Docker Desktop → Settings → Resources → File sharing에 해당 드라이브가 공유됐는지 확인. WSL2 백엔드면 프로젝트를 WSL 파일시스템(`~/`)에 두면 가장 빠름 |
| `The container name "/mini-mysql" is already in use` | 예전에 `docker run --name mini-mysql`로 만든 컨테이너가 남아 있음. `docker rm -f mini-mysql` 실행 후 `docker compose up -d --build` |
