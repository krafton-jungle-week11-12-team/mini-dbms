# Phase 1 테스트 케이스

이 문서를 읽으면 Phase 1의 각 단계를 어떤 입력으로 테스트하고, 어떤 결과를 기대하는지 알 수 있어요.
기대 결과는 [설계 문서](../design/phase1.md)를 따라요.

## 작성 방식

- 에러 종류마다 대표 입력 하나와, 동작이 갈리는 경계만 써요.
- 표 하나가 테스트 함수 하나예요. 각 행은 `pytest.mark.parametrize`의 케이스 한 줄이 돼요.
- 실행기와 스토리지 테스트는 임시 폴더(`tmp_path`)에 `users.csv`를 직접 써서 준비해요. `\n`은 줄바꿈이에요.
- 스키마는 `users(id INT, name TEXT, age INT)`예요. CSV 파일에는 머리글 없이 데이터만 있어요.

## CLI

### `test_split_statements`: `split_statements(sql)`

| ID | 시나리오 | 입력 | 기대 결과 |
| --- | --- | --- | --- |
| T-CLI-01 | 명령어 분리 | `"INSERT INTO memo VALUES (1, 'a'); SELECT * FROM memo;"` | `["INSERT INTO memo VALUES (1, 'a')", " SELECT * FROM memo"]` |
| T-CLI-02 | 빈 명령어도 결과에 포함 | `"INSERT INTO memo VALUES (1, 'a');;"` | `["INSERT INTO memo VALUES (1, 'a')", ""]` |
| T-CLI-03 | 닫히지 않은 따옴표도 그대로 | `"INSERT INTO memo VALUES (1, 'a);"` | `["INSERT INTO memo VALUES (1, 'a);"]` |

### `test_cli_error`: `main(argv)`

| ID | 시나리오 | 실행 | 기대 결과 |
| --- | --- | --- | --- |
| T-CLI-04 | 인자 없음 | `./mini-dbms` | 종료 코드 1 |
| T-CLI-05 | 인자 2개 | `./mini-dbms a.sql b.sql` | 종료 코드 1 |
| T-CLI-06 | 파일 없음 | `./mini-dbms nofile.sql` | 종료 코드 1 |
| T-CLI-07 | 빈 파일 | 공백만 있는 파일로 실행 | 종료 코드 1 |

## 토크나이저

### `test_tokenize`: `tokenize(sql)` 정상

| ID | 시나리오 | 입력 | 기대 결과 |
| --- | --- | --- | --- |
| T-TOK-01 | 키워드 대소문자 섞임 | `InsErt into users values(1, 'kim', 23)` | `[KEYWORD(INSERT), KEYWORD(INTO), IDENT(users), KEYWORD(VALUES), LPAREN, NUMBER(1), COMMA, STRING(kim), COMMA, NUMBER(23), RPAREN, EOF]` |
| T-TOK-02 | 문자열 안의 `;`, `@` | `insert into users values(1, 'k;i@m', 23)` | `[..., COMMA, STRING(k;i@m), COMMA, ...]` |
| T-TOK-03 | 음수 | `insert into users values(1, 'kim', -23)` | `[..., COMMA, NUMBER(-23), RPAREN, EOF]` |
| T-TOK-04 | 공백 없는 비교 | `select * from users where id=-5` | `[..., IDENT(id), SYMBOL(=), NUMBER(-5), EOF]` |
| T-TOK-05 | `!=` | `select * from users where id != 5` | `[..., IDENT(id), SYMBOL(!=), NUMBER(5), EOF]` |
| T-TOK-06 | `<=` 한 토큰 | `select * from users where age <= 20` | `[..., IDENT(age), SYMBOL(<=), NUMBER(20), EOF]` |

### `test_tokenize_error`: `tokenize(sql)` 에러

| ID | 시나리오 | 입력 | 기대 에러 메시지 |
| --- | --- | --- | --- |
| T-TOK-07 | 모르는 문자 | `select * from users where id = @1` | `알 수 없는 문자 '@'` |
| T-TOK-08 | 큰따옴표 | `insert into users values(1, "kim", 23)` | `알 수 없는 문자 '"'` |
| T-TOK-09 | `!` 단독 | `select * from users where id ! 5` | `'!' 뒤에는 '='가 와야 함` |
| T-TOK-10 | `-` 뒤에 숫자 없음 | `select * from users where age = - 5` | `'-' 뒤에는 숫자가 와야 함` |
| T-TOK-11 | 숫자 뒤에 문자 | `insert into users values(12abc, 'kim', 23)` | `잘못된 숫자 '12abc'` |
| T-TOK-12 | 닫히지 않은 문자열 | `insert into users values(1, 'kim, 23)` | `닫히지 않은 문자열` |
| T-TOK-13 | 소수점 | `insert into users values(1, 'kim', -23.1)` | `알 수 없는 문자 '.'` |

## 파서

### `test_parse`: `parse(tokenize(sql))` 정상

| ID | 시나리오 | 입력 | 기대 결과 |
| --- | --- | --- | --- |
| T-PAR-01 | INSERT | `INSERT INTO users VALUES (1, 'kim', 25)` | `InsertStmt { table: "users", values: [1, "kim", 25] }` |
| T-PAR-02 | SELECT * | `SELECT * FROM users` | `SelectStmt { table: "users", columns: 없음, where: 없음 }` |
| T-PAR-03 | SELECT 컬럼 + WHERE | `SELECT name, age FROM users WHERE age >= 20` | `SelectStmt { table: "users", columns: ["name", "age"], where: Condition { "age", >=, 20 } }` |
| T-PAR-04 | 빈 문장 무시 | `""` | `None` |

### `test_parse_error`: `parse(tokenize(sql))` 에러

| ID | 시나리오 | 입력 | 기대 에러 메시지 |
| --- | --- | --- | --- |
| T-PAR-05 | 키워드 오타 | `INSERT INTO users VALUE (1)` | `VALUES가 필요한데 'VALUE'가 옴` |
| T-PAR-06 | 시작 키워드 아님 | `SELEC * FROM users` | `문장은 INSERT 또는 SELECT로 시작해야 함` |
| T-PAR-07 | 키워드 누락 | `SELECT * users` | `FROM이 필요한데 'users'가 옴` |
| T-PAR-08 | 닫는 괄호 누락 | `INSERT INTO users VALUES (1, 2` | `')'가 필요한데 EOF가 옴` |
| T-PAR-09 | 쉼표 누락 | `INSERT INTO users VALUES (1 2)` | `','나 ')'가 필요한데 '2'가 옴` |
| T-PAR-10 | 값 자리에 식별자 | `SELECT * FROM users WHERE age = name` | `값이 필요한데 'name'이 옴` |
| T-PAR-11 | 남은 토큰 | `SELECT * FROM users abc` | `문장 끝이어야 하는데 'abc'가 옴` |

## 검증

### `test_validate_error`: `validate(parse(tokenize(sql)), schema)` 에러

| ID | 시나리오 | 입력 | 기대 에러 메시지 |
| --- | --- | --- | --- |
| T-VAL-01 | 없는 테이블 | `SELECT * FROM nope` | `없는 테이블 'nope'` |
| T-VAL-02 | 없는 컬럼 | `SELECT * FROM users WHERE nope = 1` | `없는 컬럼 'nope'` |
| T-VAL-03 | 값 개수 다름 | `INSERT INTO users VALUES (1, 'kim')` | `값 개수가 컬럼 수와 다름` |
| T-VAL-04 | 값 타입 다름 | `INSERT INTO users VALUES ('a', 'kim', 25)` | `컬럼 'id'의 타입과 맞지 않음` |

## 실행기

### `test_run`: `executor.run(ast)`

| ID | 시나리오 | 준비 (users.csv) | 실행 | 기대 결과 |
| --- | --- | --- | --- | --- |
| T-EXE-01 | INSERT | 빈 파일 | `run(InsertStmt { table: "users", values: [1, "kim", 23] })` | `Result { columns: [], rows: [], affected: 1 }`, 파일 내용 `1,kim,23\n` |
| T-EXE-02 | INSERT 두 번 | `1,kim,23\n` | `run(InsertStmt { table: "users", values: [2, "lee", 30] })` | 파일 내용 `1,kim,23\n2,lee,30\n` |
| T-EXE-03 | SELECT * | `1,kim,23\n` | `run(SelectStmt { table: "users", columns: 없음, where: 없음 })` | `Result { columns: ["id", "name", "age"], rows: [[1, "kim", 23]], affected: 1 }` |
| T-EXE-04 | WHERE 일치 | `1,kim,23\n2,lee,30\n` | `run(SelectStmt { table: "users", columns: 없음, where: Condition { "age", =, 23 } })` | `rows: [[1, "kim", 23]], affected: 1` |
| T-EXE-05 | WHERE 비교 연산자 | `1,kim,23\n2,lee,30\n` | `run(SelectStmt { table: "users", columns: 없음, where: Condition { "age", >=, 25 } })` | `rows: [[2, "lee", 30]], affected: 1` |
| T-EXE-06 | WHERE 문자열 | `1,kim,23\n2,lee,30\n` | `run(SelectStmt { table: "users", columns: 없음, where: Condition { "name", !=, "kim" } })` | `rows: [[2, "lee", 30]], affected: 1` |
| T-EXE-07 | WHERE 일치 없음 | `1,kim,23\n` | `run(SelectStmt { table: "users", columns: 없음, where: Condition { "age", >, 100 } })` | `Result { columns: ["id", "name", "age"], rows: [], affected: 0 }` |
| T-EXE-08 | 컬럼 순서 바꿔 조회 | `1,kim,23\n` | `run(SelectStmt { table: "users", columns: ["age", "name"], where: 없음 })` | `Result { columns: ["age", "name"], rows: [[23, "kim"]], affected: 1 }` |
| T-EXE-09 | 빈 테이블 조회 | 빈 파일 | `run(SelectStmt { table: "users", columns: 없음, where: 없음 })` | `Result { columns: ["id", "name", "age"], rows: [], affected: 0 }` |
| T-EXE-10 | 행 순서 | `2,lee,30\n1,kim,23\n` | `run(SelectStmt { table: "users", columns: 없음, where: 없음 })` | `rows: [[2, "lee", 30], [1, "kim", 23]]` (파일 순서 그대로) |

## 스토리지

### `test_storage`: `Storage`

| ID | 시나리오 | 준비 (users.csv) | 실행 | 기대 결과 |
| --- | --- | --- | --- | --- |
| T-STO-01 | 빈 파일에 추가 | 빈 파일 | `append("users", [1, "kim", 23])` | 반환값 `0`, 파일 내용 `1,kim,23\n` |
| T-STO-02 | 이어서 추가 | `1,kim,23\n` | `append("users", [2, "lee", 30])` | 반환값 `9` (앞 행의 바이트 수) |
| T-STO-03 | 한글 값의 오프셋 | `1,김,23\n` | `append("users", [2, "lee", 30])` | 반환값 `9` (`김`은 3바이트) |
| T-STO-04 | 쉼표가 든 값 | 빈 파일 | `append("users", [1, "a,b", 23])` 후 `list(scan("users"))` | `[(0, [1, "a,b", 23])]` (컬럼 3개 그대로) |
| T-STO-05 | 전체 읽기 | `1,kim,23\n2,lee,30\n` | `list(scan("users"))` | `[(0, [1, "kim", 23]), (9, [2, "lee", 30])]` |
| T-STO-06 | 빈 파일 읽기 | 빈 파일 | `list(scan("users"))` | `[]` |
| T-STO-07 | 위치로 한 행 읽기 | `1,kim,23\n2,lee,30\n` | `read_at("users", 9)` | `[2, "lee", 30]` |
| T-STO-08 | 숫자 타입 복원 | `1,kim,23\n` | `list(scan("users"))` | `23`이 문자열 `"23"`이 아니라 숫자 `23` |
