# Phase 2 체험: 100만 건에서 B+ 트리 vs 선형 탐색 (터미널 B: mysql)

> 선행 조건: [lab/README.md](../README.md)의 "0. Docker 환경 준비"를 마쳤다면 바로 시작할 수 있어요.

100만 건에서 `id`로 찾으면 0.24ms, `email`로 찾으면 165ms가 걸려 약 700배 차이가 났어요. MySQL InnoDB는 PRIMARY KEY로 B+ 트리(클러스터드 인덱스)를 만들기 때문에, 과제의 "자동 ID → B+ 트리 등록" 구조와 같아요.

## 2-1. 100만 건 만들기 (`work/phase2/setup.sql`)

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

## 2-2. 인덱스 사용 vs 선형 탐색 (`compare.sql`)

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

## 2-3. 보조 인덱스를 추가하면? (`index.sql`)

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

## 2-4. 파일로 확인하기 (선택)

```bash
ls -lh /var/lib/mysql/minidb/    # 터미널 B (mysql 컨테이너 안)
```

100만 건이 `users.ibd` 파일 하나(약 116 MB)에 들어 있어요. InnoDB는 이 파일 안에 16KB 페이지로 B+ 트리를 저장하고, 과제의 메모리 기반 B+ 트리는 이것을 단순화한 버전이에요. 이 데이터는 Docker 볼륨(`mysql-data`)에 있어서 컨테이너를 끄고 켜도 유지돼요.

---

이전: [Phase 1 체험](phase1-sqlite.md) · 다음: [Phase 3 체험](phase3-concurrency.md)
