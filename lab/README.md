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

## 단계별 체험

아래 0장으로 환경을 준비한 뒤, 하고 싶은 단계의 가이드를 열어요. 각 가이드는 혼자 읽어도 따라 할 수 있어요.

| 과제 단계 | 가이드 |
| --- | --- |
| Phase 1. SQL 처리기 | [Phase 1 체험](docs/phase1-sqlite.md) |
| Phase 2. B+ 트리 인덱스 | [Phase 2 체험](docs/phase2-bplustree.md) |
| Phase 3. API 서버 | [Phase 3 체험](docs/phase3-concurrency.md) |

체험한 내용을 우리 구현으로 옮길 계획은 [우리 구현에 가져갈 체크리스트](docs/implementation-checklist.md)에 정리했어요. 실행 중 문제가 생기면 [트러블슈팅](#트러블슈팅)을 보세요.

## 0. Docker 환경 준비

팀 저장소의 `lab/` 폴더에 이 튜토리얼의 파일이 모두 들어 있어서, 클론하고 `docker compose up -d --build` 한 번이면 끝나요. 파일을 직접 만들 필요는 없고, 0-1과 0-2는 구성을 이해하기 위한 설명이에요.

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

## 종료·초기화 명령 (`mini-dbms/lab` 폴더에서)

```bash
docker compose stop        # 잠시 멈추기 (데이터 유지)
docker compose start       # 다시 켜기
docker compose down        # 컨테이너 삭제 (MySQL 데이터는 볼륨에 남음)
docker compose down -v     # 컨테이너 + MySQL 데이터까지 완전 초기화
```

SQLite DB는 `work/phase1/mini.db` 파일만 지우면 초기화돼요.

## 트러블슈팅

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
