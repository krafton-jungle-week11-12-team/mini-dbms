# Phase 1 체험: 텍스트 SQL → CLI → 파일 저장 (터미널 A: lab)

> 선행 조건: [lab/README.md](../README.md)의 "0. Docker 환경 준비"를 마쳤다면 바로 시작할 수 있어요.

SQLite는 "`.sql` 파일을 커맨드라인으로 넘기면 파싱·실행하고 파일 하나에 저장하는" Phase 1 요구사항과 구조가 거의 같아요.

## 1-1. SQL 파일 3개 (`work/phase1/`)

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

## 1-2. CLI로 실행하기

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

## 1-3. "테이블 = 파일" 눈으로 확인하기

```bash
ls -l mini.db                    # 12288 bytes = 4KB 페이지 3개
file mini.db                     # SQLite 3.x database, ... database pages 3
strings mini.db | grep example   # 저장된 값이 바이너리 안에 그대로 보인다
```

`mini.db`는 내 PC의 `work/phase1/`에도 생기므로 DB Browser for SQLite 같은 프로그램으로 열어볼 수도 있어요. SQLite는 데이터를 CSV가 아닌 4KB 페이지 단위 바이너리로 저장하고, 우리 팀이 저장 포맷(CSV / binary / custom)을 고를 때 비교 기준이 돼요.

## 1-4. 엣지 케이스 던져보기

| 입력 | SQLite 반응 | 우리 구현에서 정해야 할 것 |
| --- | --- | --- |
| `sqlite3 mini.db "SELEC * FROM users;"` | `syntax error`와 함께 틀린 위치를 `^`로 표시 | 파서 에러 메시지에 위치 포함 여부 |
| `sqlite3 mini.db "SELECT * FROM nope;"` | `no such table: nope` | 없는 테이블(파일) 처리 |
| `sqlite3 mini.db "INSERT INTO users(name, age) VALUES('choi', 'abc');"` | 에러 없이 저장되고, `SELECT typeof(age) FROM users WHERE name='choi';`는 `text` | 타입 검사를 할지 말지 |

---

다음: [Phase 2 체험](phase2-bplustree.md)
