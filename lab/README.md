# DBMS 체험 실습 환경

이 폴더로 실제 DBMS(SQLite, MySQL 8.0)를 띄워서 과제의 Phase 1~3을 직접 구현하기 전에 미리 체험할 수 있어요.
Docker만 있으면 OS와 상관없이 모두 같은 명령으로 같은 환경을 만들 수 있어요.

| 과제 단계 | 실습에서 확인하는 것 | 실행 위치 |
| --- | --- | --- |
| Phase 1. SQL 처리기 | `.sql` 파일을 CLI로 넘겨 INSERT/SELECT를 실행하고, 테이블이 파일 하나로 저장되는 모습 | `mini-lab` (SQLite) |
| Phase 2. B+ 트리 인덱스 | 100만 건에서 `WHERE id = ?`(B+ 트리)와 다른 컬럼 조회(선형 탐색)의 속도 차이 | `mini-mysql` |
| Phase 3. API 서버 | 동시 요청 병렬 처리, 서버 스레드 재사용, 잠금이 없을 때 생기는 lost update | `mini-lab` → `mini-mysql` |

## 준비하기

- Docker Desktop(Windows, macOS) 또는 Docker Engine과 Compose 플러그인(Linux)을 설치해요.
- 처음 실행할 때 이미지를 내려받으므로 인터넷 연결과 약 1.5 GB의 디스크 공간이 필요해요.

## 실행하기

```bash
cd lab
docker compose up -d --build
docker compose ps
```

`mini-mysql`이 `(healthy)`, `mini-lab`이 `Up`으로 보이면 준비가 끝난 거예요.
처음에는 이미지를 내려받느라 1~3분 걸려요.

실습은 두 컨테이너 안에 들어가서 해요. 터미널을 두 개 열어 두면 편해요.

| 터미널 | 들어가는 명령 | 쓰는 단계 |
| --- | --- | --- |
| A (lab) | `docker compose exec lab bash` | Phase 1, Phase 3 |
| B (mysql) | `docker compose exec mysql bash` | Phase 2, Phase 3 관찰 |

내 PC의 `lab/work` 폴더는 두 컨테이너의 `/work`에 공유돼요.
SQL 파일은 평소 쓰는 에디터로 고치고, 실행은 컨테이너 안에서 해요.

## 단계별 명령

### Phase 1 (터미널 A)

```bash
cd /work/phase1
sqlite3 mini.db < schema.sql
sqlite3 mini.db < insert.sql
sqlite3 mini.db < select.sql
```

`id`를 넣지 않았는데 1, 2, 3이 자동으로 붙고, `mini.db` 파일 하나에 테이블이 저장되는 걸 확인할 수 있어요.

### Phase 2 (터미널 B)

```bash
cd /work/phase2
mysql -ujungle -pjungle1234 -t minidb < setup.sql    # 100만 건 생성 (몇 초 걸려요)
mysql -ujungle -pjungle1234 -t minidb < compare.sql  # id 조회 vs email 조회
mysql -ujungle -pjungle1234 -t minidb < index.sql    # email에 인덱스를 추가한 뒤 다시 조회
```

`SHOW PROFILES`의 실행 시간과 `EXPLAIN`의 `type` 값을 비교해 보세요.
- `const`: 기본 키(B+ 트리)로 행 하나를 바로 찾았다는 뜻이에요. `id` 조회에서 나와요.
- `ALL`: 테이블 전체를 처음부터 훑었다는 뜻이에요. 인덱스 없는 `email` 조회에서 나와요.
- `ref`: 보조 인덱스로 일치하는 행을 찾았다는 뜻이에요. `index.sql` 실행 후 `email` 조회에서 나와요.

테스트 환경에서는 `id` 조회가 0.24 ms, 인덱스 없는 `email` 조회가 165 ms였어요.

### Phase 3 (터미널 A)

Phase 2의 `users` 테이블을 쓰므로 Phase 2의 `setup.sql`을 먼저 실행해요.

```bash
python /work/phase3/concurrency.py
```

스크립트가 실행되는 동안 터미널 B에서 `mysql -ujungle -pjungle1234 -e "SHOW PROCESSLIST;"`를 실행하면 동시에 처리 중인 연결을 볼 수 있어요.
테스트 환경에서는 요청 20건이 순차 10.2초에서 병렬 1.07초로 줄었고, 잠금이 없을 때는 잔액이 200원이 아니라 110원이 됐어요.

## 종료하고 초기화하기

```bash
docker compose stop      # 잠시 멈추기 (데이터 유지)
docker compose start     # 다시 켜기
docker compose down -v   # 컨테이너와 MySQL 데이터를 모두 지우기
```

## 문제가 생기면

| 증상 | 해결 |
| --- | --- |
| `Cannot connect to the Docker daemon` | Docker Desktop을 실행하고 상태가 Running이 된 뒤 다시 실행해요. |
| `The container name "/mini-mysql" is already in use` | 예전에 `docker run`으로 만든 컨테이너가 남아 있어요. `docker rm -f mini-mysql` 후 다시 `up`해요. |
| mysql이 계속 `(health: starting)` | 처음 초기화는 30초~1분 걸려요. `docker compose logs mysql`에 `ready for connections`가 나오는지 확인해요. |
| lab에서 `Can't connect to MySQL server on '127.0.0.1'` | 컨테이너 안의 127.0.0.1은 자기 자신이에요. 호스트를 서비스 이름 `mysql`로 지정해요. |
| `Recursive query aborted after 1001 iterations` | `setup.sql` 안의 `SET SESSION cte_max_recursion_depth = 1000000;`이 INSERT보다 먼저 실행됐는지 확인해요. |
