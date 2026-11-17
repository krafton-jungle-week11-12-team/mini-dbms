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

## 설계 결정 (ADR)

- [0001. 테이블 저장 형식: CSV](docs/adr/0001-storage-format.md)
- [0002. 개발 언어: Python](docs/adr/0002-language.md)
- [0003. 서버 구조와 스레드 풀](docs/adr/0003-server-architecture.md)
- [0004. 락 전략: 테이블별 락](docs/adr/0004-locking.md)

## DBMS 체험 실습

과제를 구현하기 전에 SQLite와 MySQL로 Phase 1~3을 미리 체험하려면 [lab/README.md](lab/README.md)를 따라 해요.
