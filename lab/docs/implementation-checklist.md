# 우리 구현에 가져갈 체크리스트

> 이 문서는 실습이 아니라 구현 계획이에요. [lab/README.md](../README.md)의 Phase 1~3 체험에서 확인한 동작을 우리 미니 DBMS에 어떻게 옮길지 정리했어요.

체험에서 확인한 동작을 우리 미니 DBMS의 기능 테스트 기준으로 그대로 쓸 수 있고, 같은 compose 환경에 우리 서버를 서비스로 추가하면 Phase 3 데모 환경으로도 이어져요.

- [ ] Phase 1: `./mini-dbms query.sql`처럼 SQL 파일을 받아 INSERT/SELECT 실행, 문법 오류·없는 테이블·타입 오류 메시지 정의
- [ ] Phase 1: 저장 포맷 결정 (CSV는 단순, SQLite처럼 페이지 단위 바이너리는 빠름)
- [ ] Phase 2: INSERT 시 자동 id 부여 → B+ 트리에 (id → 레코드 위치) 등록
- [ ] Phase 2: `WHERE id = ?`일 때만 인덱스 경로, 나머지는 선형 탐색. `EXPLAIN`처럼 어느 경로를 탔는지 출력하면 발표 때 보여주기 좋음
- [ ] Phase 2: 100만 건 생성 스크립트와 속도 비교표 ([Phase 2 체험](phase2-bplustree.md)의 2-2 표와 같은 형식)
- [ ] Phase 3: 고정 크기 Thread Pool + 작업 큐, 요청별 스레드 할당
- [ ] Phase 3: 동시 INSERT 시 id 중복·B+ 트리 손상을 막는 락 설계, [Phase 3 체험](phase3-concurrency.md)의 3-2 스크립트 같은 동시성 테스트
- [ ] Phase 3: 우리 API 서버도 `Dockerfile` + `compose.yaml` 서비스로 만들어 `docker compose up` 한 번으로 데모되게 하기
