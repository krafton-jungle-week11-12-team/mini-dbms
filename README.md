# mini-DBMS

SQL 파일을 읽어 `INSERT`와 `SELECT`를 실행하고, 데이터를 CSV 파일에 저장하는 작은 DBMS예요.

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

### 대량 데이터와 성능 비교

```
python scripts/gen_data.py --rows 1000000
python scripts/bench.py --repeat 5
```

- `gen_data.py`는 `data/users.csv`를 새로 써요. 들어 있던 데이터는 지워져요.
  - `--mode csv`(기본): 저장 계층과 같은 형식으로 CSV에 바로 써요. 100만 건이 몇 초 안에 만들어져요.
  - `--mode engine`: SQL 처리기로 INSERT해서 id 자동 부여와 인덱스 등록까지 실제 경로를 거쳐요. 느려서 1만 건 정도로 써요.
  - `--mode sql --out bulk.sql`: `./mini-dbms bulk.sql`로 실행할 SQL 파일을 만들어요.
  - `name`은 `user<id>`로 만들어서, id 조회와 name 조회가 같은 행을 찾아요.
- `bench.py`는 엔진을 한 번만 만든 뒤, 같은 행을 `WHERE id = ?`(B+ 트리)와 `WHERE name = ?`(선형 탐색)으로 여러 번 조회해 평균을 내요. 조회는 SQL 문장을 `engine.execute()`에 넘겨서 Phase 1 처리기를 그대로 거치고, 두 결과가 같은지도 확인해요.

결과: 100만 건, 5회 평균, Python 3.10.12 (Windows 노트북 위 Linux VM). 엔진 기동(인덱스 재구축)은 6.51초 걸렸어요.

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
