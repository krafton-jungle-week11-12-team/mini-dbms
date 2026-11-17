# Phase 3 테스트 케이스

이 문서를 읽으면 Phase 3 API 서버가 요청마다 어떤 상태 코드와 응답을 돌려줘야 하는지, 엔진에 추가한 `Result` 필드와 `TableNotFoundError`를 어떻게 테스트하는지 알 수 있어요.
기대 결과는 [Phase 3 설계](../design/phase3.md)와 [Phase 3 요구사항](../requirements/phase3.md)을 따라요.

## 작성 방식

- 상태 코드마다 대표 요청 하나와, 동작이 갈리는 경계만 써요.
- 서버 테스트(`T-SRV`)는 임시 폴더(`tmp_path`)를 데이터 폴더로 서버를 띄우고 실제 HTTP 요청을 보내요.
- 모든 서버 응답은 바디의 `ok`와, 실패면 `error.code`까지 확인해요. 그래서 공통 응답 구조(`SRV-06`)는 케이스를 따로 두지 않아요.
- ID는 Phase 1·2 번호에 이어서 붙여요. 서버는 `T-SRV-01`부터 시작해요.
- 스키마는 `users(id INT, name TEXT, age INT)`이고, id는 실행기가 부여해요.
- 상태는 `미실행`, `통과`, `실패` 중 하나예요.

## 테스트 케이스

| ID | 분류 | 시나리오 | 준비 (Given) | 실행 (When) | 기대 결과 (Then) | 상태 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-SRV-01 | 서버 | SELECT 성공 | 서버 실행, `users`에 id 1~3 행 저장 | `POST /query` `{"sql": "SELECT * FROM users WHERE id = 3"}` | 200, `ok: true`, `type: "select"`, `columns: ["id", "name", "age"]`, `rows`에 id 3 행 하나, `row_count: 1` | 미실행 | `SRV-01` |
| T-SRV-02 | 서버 | INSERT 성공 | 서버 실행, 빈 `users` | `POST /query` `{"sql": "INSERT INTO users VALUES ('kim', 25)"}` | 201, `ok: true`, `type: "insert"`, `inserted_id: 1`, `affected_rows: 1` | 미실행 | `SRV-02` |
| T-SRV-03 | 서버 | 끝의 세미콜론 허용 | 서버 실행, `users`에 id 1~3 행 저장 | `POST /query` `{"sql": "SELECT * FROM users;"}` | 200, `ok: true`, `row_count: 3` | 미실행 | `"SELECT * FROM users;;"`도 같은 결과 |
| T-SRV-04 | 서버 | SQL 문법 오류 | 서버 실행 | `POST /query` `{"sql": "SELECT * FORM users"}` | 400, `ok: false`, `error.code: "SYNTAX_ERROR"` | 미실행 | `SRV-03` |
| T-SRV-05 | 서버 | 없는 테이블 | 서버 실행 | `POST /query` `{"sql": "SELECT * FROM orders"}` | 404, `ok: false`, `error.code: "TABLE_NOT_FOUND"`, `error.message: "없는 테이블 'orders'"` | 미실행 | `SRV-03` |
| T-SRV-06 | 서버 | 엔진 내부 오류 | 서버 실행, `engine.execute`가 `RuntimeError`를 던지도록 교체 | `POST /query` `{"sql": "SELECT * FROM users"}` | 500, `ok: false`, `error.code: "INTERNAL_ERROR"`, `error.message: "internal server error"`, 서버 로그에 예외 기록 | 미실행 | `SRV-03`, `SRV-05`. 응답에 예외 내용이 없어야 함 |
| T-SRV-07 | 서버 | 실패 후 다음 요청 정상 처리 | T-SRV-06 요청을 보낸 뒤, `engine.execute` 원래대로 복구 | `POST /query` `{"sql": "SELECT * FROM users"}` | 200, `ok: true` | 미실행 | `SRV-05` |
| T-SRV-08 | 서버 | 없는 경로 | 서버 실행 | `POST /abc` `{"sql": "SELECT * FROM users"}` | 404, `ok: false`, `error.code: "NOT_FOUND"` | 미실행 | `SRV-04` |
| T-SRV-09 | 서버 | POST가 아닌 메서드 | 서버 실행 | `GET /query` | 405, `ok: false`, `error.code: "METHOD_NOT_ALLOWED"` | 미실행 | `SRV-04` |
| T-SRV-10 | 서버 | JSON이 아닌 Content-Type | 서버 실행 | `POST /query`, `Content-Type: text/plain`, 바디 `SELECT * FROM users` | 415, `ok: false`, `error.code: "UNSUPPORTED_MEDIA_TYPE"` | 미실행 | `SRV-04` |
| T-SRV-11 | 서버 | 바디 1MB 초과 | 서버 실행 | `POST /query`, 바디 1,048,577바이트 | 413, `ok: false`, `error.code: "PAYLOAD_TOO_LARGE"` | 미실행 | `SRV-04` |
| T-SRV-12 | 서버 | JSON 파싱 실패 | 서버 실행 | `POST /query` 바디 `{"sql": ` | 400, `ok: false`, `error.code: "INVALID_JSON"` | 미실행 | `SRV-04` |
| T-SRV-13 | 서버 | `sql` 필드 없음 | 서버 실행 | `POST /query` `{"query": "SELECT * FROM users"}` | 400, `ok: false`, `error.code: "INVALID_REQUEST"` | 미실행 | `SRV-04` |
| T-SRV-14 | 서버 | 여러 문장 | 서버 실행 | `POST /query` `{"sql": "SELECT * FROM users; SELECT * FROM users"}` | 400, `ok: false`, `error.code: "MULTIPLE_STATEMENTS"` | 미실행 | `SRV-04` |
| T-EXE-17 | 실행기 | INSERT 결과에 `type`, `inserted_id` | 빈 `users`로 `Executor` 생성 | `INSERT INTO users VALUES ('kim', 25)` 실행 | `Result.type == "insert"`, `Result.inserted_id == 1`, `Result.affected == 1` | 미실행 | |
| T-EXE-18 | 실행기 | 인덱스 조회 시 `used_index` 참 | `users`에 id 1~3 행 저장 | `SELECT * FROM users WHERE id = 2` 실행 | `Result.type == "select"`, `Result.used_index is True`, `Result.affected == 1` | 미실행 | |
| T-EXE-19 | 실행기 | 선형 탐색 시 `used_index` 거짓 | `users`에 id 1~3 행 저장 | `SELECT * FROM users WHERE age > 20` 실행 | `Result.type == "select"`, `Result.used_index is False` | 미실행 | |
| T-VAL-08 | 검증 | 없는 테이블은 `TableNotFoundError` | 기본 스키마 | `SELECT * FROM orders` 검증 | `TableNotFoundError`, 메시지 `없는 테이블 'orders'` | 미실행 | `ValidationError`로도 잡혀야 함 (CLI 호환) |
