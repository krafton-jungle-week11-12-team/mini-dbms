# mini-DBMS

▎ SQL로 데이터를 넣고 조회하면 CSV 파일에 영구 저장하는 작은 DBMS예요. SQL 파일이나 HTTP 요청으로 INSERT/SELECT를 실행할 수 있어요.

## 사용법

Python 3.10 이상이 필요하고, 표준 라이브러리만 써요.
실행 방법은 두 가지예요. 엔진을 직접 켜서 SQL 파일을 실행하거나, API 서버를 띄워 HTTP로 SQL을 보내요.
두 방법 모두 프로젝트 루트에서 실행하고, 데이터는 같은 폴더(`MINI_DBMS_DATA`, 기본 `data`)에 테이블마다 `<테이블>.csv` 파일로 저장돼요.

### 지원하는 SQL

테이블은 아래 세 개예요. 스키마를 바꾸는 방법은 [스키마와 인덱스 설정](#스키마와-인덱스-설정)을 봐요.

| 테이블 | 컬럼 |
|---|---|
| `users` | `id INT, name TEXT, age INT` |
| `messages` | `id INT, author TEXT, content TEXT, created_at INT, client_id TEXT` |
| `likes` | `id INT, message_id INT, created_at INT` |

id는 INSERT할 때 1부터 자동으로 붙으니, 값에는 id를 뺀 나머지 컬럼을 스키마 순서대로 써요. 예: `INSERT INTO users VALUES ('kim', 25)`

```
INSERT INTO <테이블> VALUES (<값>, <값>, ...)
SELECT * | <컬럼>, ... FROM <테이블> [WHERE <컬럼> <연산자> <값>]
```

- 값: 정수(`25`, `-5`) 또는 작은따옴표 문자열(`'kim'`, `'it''s'`)
- 연산자: `=` `!=` `<` `>` `<=` `>=`
- `WHERE id = <값>`은 B+ 트리 인덱스로 한 행만 읽어요.
- `WHERE <보조 인덱스 컬럼> = <값>`(`messages.client_id`, `likes.message_id`)은 보조 인덱스로 일치하는 행만 읽어요.
- 그 외 조건(`!=`, `<` 같은 비교 포함)은 모든 행을 훑어요.
- `AND`/`OR`, `ORDER BY`, INSERT의 컬럼 목록 지정은 지원하지 않아요.

자세한 내용은 [Phase 1 설계](docs/design/phase1.md)와 [Phase 2 설계](docs/design/phase2.md)를 봐요.

### 스키마와 인덱스 설정

테이블과 인덱스는 SQL(`CREATE TABLE`, `CREATE INDEX`)이 아니라 `mini_dbms/engine.py`의 설정 세 개로 정해요. 고친 뒤 엔진이나 서버를 다시 켜면 반영돼요.

| 설정 | 하는 일 |
|---|---|
| `SCHEMA` | 테이블과 컬럼(이름, `INT` 또는 `TEXT`)을 정해요. 컬럼 순서가 CSV 파일의 열 순서이자 INSERT 값의 순서예요. |
| `INDEX_KEYS` | 테이블마다 기본 키 컬럼 하나를 정해요. 이 컬럼은 INSERT 때 1부터 자동으로 붙고, `WHERE <컬럼> = <값>` 조회에 B+ 트리를 써요. 값이 겹치지 않아요. |
| `SECONDARY_INDEXES` | 테이블마다 보조 인덱스 컬럼 목록을 정해요. 값이 겹쳐도 되고, `WHERE <컬럼> = <값>` 조회에 B+ 트리를 써서 일치하는 행만 읽어요. |

```python
SCHEMA = {
    "users": [("id", "INT"), ("name", "TEXT"), ("age", "INT")],
    "messages": [("id", "INT"), ("author", "TEXT"), ("content", "TEXT"), ("created_at", "INT"), ("client_id", "TEXT")],
    "likes": [("id", "INT"), ("message_id", "INT"), ("created_at", "INT")],
}

INDEX_KEYS = {"users": "id", "messages": "id", "likes": "id"}

SECONDARY_INDEXES = {
    "messages": ["client_id"],
    "likes": ["message_id"],
}
```

- **테이블 추가**: `SCHEMA`에 테이블을 넣고, `INDEX_KEYS`에 기본 키 컬럼(보통 `id`, `INT`)을 적어요. 빠뜨리면 `id`를 써요.
- **보조 인덱스 추가**: `SECONDARY_INDEXES`의 해당 테이블 목록에 컬럼 이름을 넣어요. 실행기 코드는 고치지 않아도 돼요.
- 인덱스는 파일에 저장하지 않고, 시작할 때 CSV를 한 번 읽어 기본 키와 보조 인덱스를 함께 다시 만들어요. 그래서 인덱스를 더하거나 빼도 데이터 파일은 그대로 써요.
- 보조 인덱스는 `=` 조회에만 쓰고, 컬럼 하나씩만 걸 수 있어요(복합 인덱스 없음). 인덱스가 늘수록 INSERT마다 갱신할 트리와 메모리가 늘어나니 자주 조회하는 컬럼에만 걸어요.
- `SECONDARY_INDEXES`에 `SCHEMA`에 없는 컬럼을 적으면 시작할 때 에러가 나요.
- **기존 테이블의 컬럼을 바꾸면** 이미 저장된 `<테이블>.csv`의 행과 열이 맞지 않아요. 개발 중에는 그 테이블의 CSV 파일을 지우고 다시 시작해요.
- SELECT 응답의 `used_index`, `index_column`으로 어떤 인덱스를 썼는지 확인할 수 있어요.

## 1. 엔진 직접 실행

HTTP 없이 엔진을 바로 호출해요. SQL 파일 실행(CLI)과 벤치마크가 이 방식이에요.

### SQL 파일 실행

문장은 `;`로 구분해요.

```sql
INSERT INTO users VALUES ('kim', 25);
INSERT INTO users VALUES ('lee', 17);
SELECT name, age FROM users WHERE age >= 20;
```

```
./mini-dbms demo.sql
```

```
1행 삽입
1행 삽입
+------+-----+
| name | age |
+------+-----+
| kim  | 25  |
+------+-----+
(1행)
```

- 다른 데이터 폴더를 쓰려면 `MINI_DBMS_DATA=경로 ./mini-dbms demo.sql`처럼 실행해요.
- 에러가 난 문장은 메시지를 출력하고 건너뛰어요. 하나라도 실패하면 종료 코드가 1이에요.

### 대량 데이터 탐색 벤치마크

서버를 거치지 않고 `engine.execute()`를 직접 불러서, HTTP 처리 시간이 섞이지 않아요.

```
python3 scripts/gen_data.py --rows 1000000
python3 scripts/bench.py --repeat 5
```

- 두 스크립트는 `MINI_DBMS_DATA`가 아니라 `--data-dir`(기본 `data`)로 폴더를 정해요.
- `gen_data.py`는 `users.csv`를 **새로 써요.** 서버나 CLI로 넣은 데이터를 지키려면 `--data-dir bench-data`처럼 다른 폴더를 쓰고, `bench.py`에도 같은 `--data-dir`을 줘요.
- 결과: 100만 건, 5회 평균, Python 3.10.12 (Windows 노트북 위 Linux VM). 엔진 기동(인덱스 재구축)은 6.51초 걸렸어요.

| 찾는 행 | id | id 조회 (ms) | name 조회 (ms) | 배수 |
| --- | ---: | ---: | ---: | ---: |
| 처음 | 1 | 9.630 | 4,644.5 | 482배 |
| 가운데 | 500,000 | 9.598 | 4,714.2 | 491배 |
| 끝 | 1,000,000 | 7.857 | 4,647.3 | 592배 |
| 없음 | 1,000,001 | 0.069 | 4,646.4 | 67,311배 |

- id 조회는 찾는 행의 위치와 상관없이 비슷해요. 시간 대부분은 `read_at()`이 파일을 열어 한 줄 읽는 데 써요. 없는 id는 트리에서 바로 끝나서 파일을 열지 않아요.
- name 조회는 이름이 겹칠 수 있어서, 찾는 행이 맨 앞에 있어도 파일 끝까지 훑어요.

## 2. API 서버 실행

### 서버 켜기

```
python3 -m mini_dbms.server
```

잘 떴으면 아래 로그가 나오고, 터미널은 요청을 기다려요. 끌 때는 `Ctrl+C`를 눌러요.

```
... INFO listening on http://127.0.0.1:8000/query
```

| 하고 싶은 것 | 명령 |
| --- | --- |
| 포트 바꾸기 | `python3 -m mini_dbms.server --port 9000` |
| 데이터 폴더 바꾸기 | `MINI_DBMS_DATA=/tmp/db python3 -m mini_dbms.server` |
| 다른 컴퓨터에서 접속 허용 | `python3 -m mini_dbms.server --host 0.0.0.0` |
| 워커 수 바꾸기 (기본 4) | `python3 -m mini_dbms.server --workers 8` |
| 작업 큐 크기 바꾸기 (기본 16) | `python3 -m mini_dbms.server --queue-size 32` |

- 데이터는 서버를 실행한 컴퓨터에 저장돼요. 요청을 보낸 쪽에는 응답만 와요.
- 서버는 시작할 때 테이블마다 CSV를 한 번 읽어 인덱스를 만들어요. 서버가 켜져 있는 동안 CLI로 넣은 데이터는 서버를 다시 켜야 보여요.
- 요청은 워커 스레드가 동시에 처리해요. 워커가 모두 바쁘면 요청이 작업 큐에서 기다리고, 큐가 가득 차면 503으로 거절해요. 워커 수(`--workers`, 기본 4)와 큐 크기(`--queue-size`, 기본 16)는 1 이상의 정수로 정해요.
- 같은 테이블의 INSERT와 SELECT는 테이블 락으로 하나씩 실행돼서, id가 겹치거나 쓰는 도중의 행을 읽지 않아요.
- 요청 바디를 5초 동안 보내지 않으면 응답 없이 연결을 닫아요.
- `Address already in use`가 나오면 `--port`로 다른 포트를 써요.

### 요청 보내기

다른 터미널에서 SQL 한 문장을 `POST /query`의 `sql` 필드에 담아 보내요. 끝의 `;`는 있어도 되고 없어도 돼요.

```
curl -X POST http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "INSERT INTO users VALUES ('"'"'kim'"'"', 25)"}'

curl -X POST http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM users WHERE id = 1"}'
```

`'"'"'`는 셸에서 작은따옴표 하나를 넣는 방법이에요.

```json
{"ok": true, "type": "insert", "inserted_id": 1, "affected_rows": 1, "elapsed_ms": 0.469}
{"ok": true, "type": "select", "columns": ["id", "name", "age"], "rows": [[1, "kim", 25]], "row_count": 1, "used_index": true, "index_column": "id", "elapsed_ms": 0.166}
```

SELECT는 200, INSERT는 201로 응답해요. 실패하면 `ok`가 `false`이고, `error.code`로 원인을 알려줘요.

```json
{"ok": false, "error": {"code": "TABLE_NOT_FOUND", "message": "없는 테이블 'orders'"}}
```

| 상태 코드 | `error.code` | 원인 |
| --- | --- | --- |
| 400 | `SYNTAX_ERROR`, `INVALID_VALUE` | SQL 문법 오류, 값 개수·타입이나 컬럼이 스키마와 안 맞음 |
| 400 | `INVALID_JSON`, `INVALID_REQUEST`, `EMPTY_SQL`, `MULTIPLE_STATEMENTS` | 요청 바디가 잘못됨 |
| 404 | `TABLE_NOT_FOUND` / `NOT_FOUND` | 없는 테이블 / `/query`가 아닌 경로 |
| 405, 411, 413, 415 | `METHOD_NOT_ALLOWED` 등 | POST가 아님, `Content-Length` 없음, 바디 1MB 초과, JSON이 아닌 `Content-Type` |
| 500 | `INTERNAL_ERROR` | 서버 내부 오류. 상세는 서버 로그에만 남아요 |
| 503 | `SERVICE_UNAVAILABLE` | 작업 큐가 가득 참. `Retry-After: 1` 헤더가 붙으니 1초 뒤 다시 보내요 |

전체 규칙은 [Phase 3 설계](docs/design/phase3.md)를, 스레드 풀과 테이블 락은 [Phase 4 설계](docs/design/phase4.md)를 봐요.

## 테스트

```
pip install pytest
pytest
```

## 설계 결정 (ADR)

- [0001. 테이블 저장 형식: CSV](docs/adr/0001-storage-format.md)
- [0002. 개발 언어: Python](docs/adr/0002-language.md)
- [0003. 서버 구조와 스레드 풀](docs/adr/0003-server-architecture.md)
- [0004. 락 전략: 테이블별 락](docs/adr/0004-locking.md)

## DBMS 체험 실습

과제를 구현하기 전에 SQLite와 MySQL로 Phase 1~3을 미리 체험하려면 [lab/README.md](lab/README.md)를 따라 해요.
