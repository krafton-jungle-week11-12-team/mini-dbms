# mini-DBMS

SQL 파일이나 HTTP 요청으로 `INSERT`와 `SELECT`를 실행하고, 데이터를 CSV 파일에 저장하는 작은 DBMS예요.

## 사용법

Python 3.9 이상이 필요하고, 표준 라이브러리만 써요.

### 1. SQL 파일 작성

테이블은 `users(id INT, name TEXT, age INT)` 하나예요. 문장은 `;`로 구분해요.
id는 INSERT할 때 1부터 자동으로 붙으니, 값에는 `name`, `age`만 써요.

```sql
INSERT INTO users VALUES ('kim', 25);
INSERT INTO users VALUES ('lee', 17);
SELECT name, age FROM users WHERE age >= 20;
```

### 2. 실행

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

- 데이터는 현재 폴더의 `data/users.csv`에 저장돼요. 다른 폴더를 쓰려면 `MINI_DBMS_DATA=경로 ./mini-dbms demo.sql`처럼 실행해요.
- 에러가 난 문장은 메시지를 출력하고 건너뛰어요. 하나라도 실패하면 종료 코드가 1이에요.

### API 서버

```
python3 -m mini_dbms.server --port 8000
```

- 데이터 폴더는 CLI와 같이 `MINI_DBMS_DATA`(기본 `data`)를 써요. `--host`의 기본값은 `127.0.0.1`이에요.
- 요청은 한 번에 하나씩 처리해요. 워커 풀은 아직 없어요.

SQL 한 문장을 `POST /query`의 `sql` 필드에 담아 보내요. 끝의 `;`는 있어도 되고 없어도 돼요.

```
curl -X POST http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM users WHERE id = 1"}'
```

```json
{"ok": true, "type": "select", "columns": ["id", "name", "age"], "rows": [[1, "kim", 25]], "row_count": 1, "used_index": true, "elapsed_ms": 0.166}
```

INSERT는 201로 `{"ok": true, "type": "insert", "inserted_id": 1, "affected_rows": 1, ...}`를 응답해요.
실패하면 `ok`가 `false`이고, `error.code`로 원인을 알려줘요.

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

전체 규칙은 [Phase 3 설계](docs/design/phase3.md)를 봐요.

### 지원하는 문법

```
INSERT INTO <테이블> VALUES (<값>, <값>, ...)
SELECT * | <컬럼>, ... FROM <테이블> [WHERE <컬럼> <연산자> <값>]
```

- 값: 정수(`25`, `-5`) 또는 작은따옴표 문자열(`'kim'`, `'it''s'`)
- 연산자: `=` `!=` `<` `>` `<=` `>=`
- `WHERE id = <값>`은 B+ 트리 인덱스로 한 행만 읽고, 그 외 조건은 모든 행을 훑어요.
- `AND`/`OR`, `ORDER BY`, INSERT의 컬럼 목록 지정은 지원하지 않아요.

자세한 내용은 [Phase 1 설계](docs/design/phase1.md)와 [Phase 2 설계](docs/design/phase2.md)를 봐요.

### 테스트

```
pip install pytest
pytest
```

### 대량 데이터 탐색 벤치마크

```
python scripts/gen_data.py --rows 1000000
python scripts/bench.py --repeat 5
```
- 결과: 100만 건, 5회 평균, Python 3.10.12 (Windows 노트북 위 Linux VM). 엔진 기동(인덱스 재구축)은 6.51초 걸렸어요.

| 찾는 행 | id | id 조회 (ms) | name 조회 (ms) | 배수 |
| --- | ---: | ---: | ---: | ---: |
| 처음 | 1 | 9.630 | 4,644.5 | 482배 |
| 가운데 | 500,000 | 9.598 | 4,714.2 | 491배 |
| 끝 | 1,000,000 | 7.857 | 4,647.3 | 592배 |
| 없음 | 1,000,001 | 0.069 | 4,646.4 | 67,311배 |

- id 조회는 찾는 행의 위치와 상관없이 비슷해요. 시간 대부분은 `read_at()`이 파일을 열어 한 줄 읽는 데 써요. 없는 id는 트리에서 바로 끝나서 파일을 열지 않아요.
- name 조회는 이름이 겹칠 수 있어서, 찾는 행이 맨 앞에 있어도 파일 끝까지 훑어요.

## 설계 결정 (ADR)

- [0001. 테이블 저장 형식: CSV](docs/adr/0001-storage-format.md)
- [0002. 개발 언어: Python](docs/adr/0002-language.md)
- [0003. 서버 구조와 스레드 풀](docs/adr/0003-server-architecture.md)
- [0004. 락 전략: 테이블별 락](docs/adr/0004-locking.md)

## DBMS 체험 실습

과제를 구현하기 전에 SQLite와 MySQL로 Phase 1~3을 미리 체험하려면 [lab/README.md](lab/README.md)를 따라 해요.
