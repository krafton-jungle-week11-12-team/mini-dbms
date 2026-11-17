# Phase 3 설계

이 문서를 읽으면 API 서버가 HTTP 요청을 어떤 순서로 검사하고, 엔진 결과와 예외를 어떤 HTTP 응답으로 바꾸는지 알 수 있어요.
요구사항은 [Phase 3 요구사항](../requirements/phase3.md)에, 서버와 엔진의 연결 방식은 [ADR 0003](../adr/0003-server-architecture.md)에 있어요.

## 처리 흐름

```
클라이언트 ──→ HTTP 요청 ──→ 요청 검사 ──→ engine.execute(sql) ──→ Result ──→ 성공 응답 (200/201)
                               │                  │
                               │ 실패              │ 예외
                               ↓                  ↓
                           에러 응답 (4xx)      예외 변환 ──→ 에러 응답 (400/404/500)
```

- 서버는 SQL을 해석하지 않아요. 문법, 테이블, 값 검사는 엔진이 해요.
- 서버는 HTTP 요청 형식만 검사하고, 엔진의 `Result`와 예외를 HTTP 응답으로 바꿔요.

## 목차

1. [요청 형식](#요청-형식)
2. [요청 검사](#요청-검사)
3. [엔진 호출](#엔진-호출)
4. [엔진 예외 변환](#엔진-예외-변환)
5. [응답 구조](#응답-구조)
6. [디버깅용 필드](#디버깅용-필드)

## 요청 형식

이 항목을 읽으면 클라이언트가 SQL을 어떤 형식으로 보내야 하는지 알 수 있어요.

SELECT와 INSERT 모두 `POST /query`로 보내고, SQL 한 문장을 바디의 `sql` 필드에 담아요.

```
POST /query  {"sql": "SELECT * FROM users WHERE id = 3"}
POST /query  {"sql": "INSERT INTO users VALUES ('kim', 25)"}
```

HTTP 요청 전체는 아래와 같아요.

```http
POST /query HTTP/1.1
Content-Type: application/json
Content-Length: 43

{"sql": "SELECT * FROM users WHERE id = 3"}
```

| 항목 | 의미 | 예시 |
| --- | --- | --- |
| `sql` | 실행할 SQL 한 문장. 끝의 `;`는 있어도 되고 없어도 돼요 | `"SELECT * FROM users WHERE id = 3;"` |
| 그 밖의 필드 | 무시해요 | `{"sql": "...", "foo": 1}` |

## 요청 검사

이 항목을 읽으면 서버가 엔진을 호출하기 전에 무엇을 어떤 순서로 검사하는지 알 수 있어요.

위에서부터 차례로 검사하고, 처음 실패한 검사의 상태 코드로 바로 응답해요.
바디를 읽기 전에 크기(6번)를 먼저 확인해서, 1MB를 넘는 바디는 읽지 않아요.

| 순서 | 검사 | 실패 조건 | 상태 코드 | `error.code` |
| --- | --- | --- | --- | --- |
| 1 | 경로 | `/query`가 아님 | 404 | `NOT_FOUND` |
| 2 | 메서드 | `POST`가 아님 | 405 | `METHOD_NOT_ALLOWED` |
| 3 | `Content-Type` | `application/json`이 아님 (`; charset=utf-8` 같은 파라미터는 허용) | 415 | `UNSUPPORTED_MEDIA_TYPE` |
| 4 | `Content-Length` 존재 | 헤더가 없음 | 411 | `LENGTH_REQUIRED` |
| 5 | `Content-Length` 형식 | 0 이상의 정수가 아님 | 400 | `INVALID_REQUEST` |
| 6 | 바디 크기 | 1MB(1,048,576바이트) 초과 | 413 | `PAYLOAD_TOO_LARGE` |
| 7 | 인코딩 | UTF-8로 디코딩 실패 | 400 | `INVALID_REQUEST` |
| 8 | JSON 파싱 | JSON이 아님 | 400 | `INVALID_JSON` |
| 9 | 최상위 타입 | 객체(`{}`)가 아님 (배열, 문자열 등) | 400 | `INVALID_REQUEST` |
| 10 | `sql` 필드 | 없음 | 400 | `INVALID_REQUEST` |
| 11 | `sql` 타입 | 문자열이 아님 (`123`, `null` 등) | 400 | `INVALID_REQUEST` |
| 12 | `sql` 내용 | 공백만 있거나 빈 문자열 (끝의 `;`를 뺀 뒤 기준) | 400 | `EMPTY_SQL` |
| 13 | 문장 수 | 끝의 `;`를 뺀 뒤에도 문장이 2개 이상 | 400 | `MULTIPLE_STATEMENTS` |

12번과 13번은 [Phase 1의 `split_statements()`](phase1.md#문장-분리)로 나눈 뒤, 빈 문장을 빼고 남은 문장 수로 판단해요.
문자열 안의 `;`(`'a;b'`)는 문장 구분자로 세지 않아요.

## 엔진 호출

이 항목을 읽으면 서버가 엔진을 어떻게 호출하고 결과를 받는지 알 수 있어요.

요청 검사를 통과한 SQL 한 문장을 `engine.execute(sql)`에 넘기고 `Result`를 받아요.
`Result`의 기존 필드는 [Phase 1 결과 형식](phase1.md#결과-형식)과 같고, Phase 3에서 필드 세 개를 추가해요([디버깅용 필드](#디버깅용-필드)).

## 엔진 예외 변환

이 항목을 읽으면 엔진이 던진 예외가 어떤 상태 코드로 바뀌는지 알 수 있어요.

| 예외 | 상태 코드 | `error.code` |
| --- | --- | --- |
| `TableNotFoundError` | 404 | `TABLE_NOT_FOUND` |
| `TokenizeError`, `ParseError` | 400 | `SYNTAX_ERROR` |
| `ValidationError` | 400 | `INVALID_VALUE` |
| `DbError`가 아닌 모든 예외 | 500 | `INTERNAL_ERROR` |

`TableNotFoundError`는 `ValidationError`의 자식이라, 서버는 `TableNotFoundError`를 먼저 잡아요.

### 400: 클라이언트가 보낸 SQL이 잘못됨

엔진의 에러는 모두 `DbError`를 상속해요. 단계별로 세 종류가 있어요.

**토크나이저 (`TokenizeError`)**: 글자 단위로 읽을 수 없는 경우

| SQL | 엔진 메시지 |
| --- | --- |
| `SELECT * FROM users WHERE name = 'kim` | 닫히지 않은 문자열 |
| `SELECT * FROM users WHERE id = 3 #` | 알 수 없는 문자 '#' |
| `SELECT * FROM users WHERE age ! 3` | '!' 뒤에는 '='가 와야 함 |
| `INSERT INTO users VALUES ('kim', 2a)` | 잘못된 숫자 '2a' |

**파서 (`ParseError`)**: 토큰은 맞지만 문법이 틀린 경우

| SQL | 엔진 메시지 |
| --- | --- |
| `SELECT * FORM users` | `FROM`이 필요한데 다른 토큰이 옴 |
| `INSERT INTO users VALUES ('kim' 25)` | ','나 ')'가 필요한데 25가 옴 |
| `SELECT * FROM users WHERE id = 3 LIMIT 1` | 문장 끝이어야 하는데 LIMIT이 옴 |
| `UPDATE users SET age = 26` | 문장은 INSERT 또는 SELECT로 시작해야 함 (지원하지 않는 문장) |

**AST 검증 (`ValidationError`)**: 문법은 맞지만 스키마와 안 맞는 경우

| SQL | 엔진 메시지 |
| --- | --- |
| `INSERT INTO users VALUES ('kim')` | 값 개수가 컬럼 수와 다름 |
| `INSERT INTO users VALUES (25, 'kim')` | 컬럼 'name'의 타입과 맞지 않음 |
| `SELECT * FROM users WHERE email = 'a'` | 없는 컬럼 'email' |
| `SELECT * FROM users WHERE age = 'abc'` | 컬럼 'age'의 타입과 맞지 않음 |

### 404: 없는 테이블

지금은 없는 테이블도 `ValidationError`로 던져서 400과 구분할 수 없어요.
`errors.py`에 `ValidationError`를 상속하는 `TableNotFoundError`를 추가하고, `validator.py`가 없는 테이블에서 이 예외를 던지게 바꿔요.
`DbError`를 잡는 CLI는 바꾸지 않아도 돼요.

| SQL | 엔진 메시지 |
| --- | --- |
| `SELECT * FROM orders` | 없는 테이블 'orders' |
| `INSERT INTO user VALUES ('kim', 25)` (오타) | 없는 테이블 'user' |

### 500: 클라이언트 잘못이 아님 (`DbError`가 아닌 예외)

SQL은 정상인데 서버 쪽 문제로 실패하는 경우예요.
클라이언트에는 `"internal server error"`만 보내고, 예외 상세와 스택 트레이스는 서버 로그에만 남겨요.

| 상황 | 예외 | 어디서 |
| --- | --- | --- |
| 데이터 폴더 권한이 없거나 디스크가 가득 참 | `PermissionError`, `OSError` | `storage.append()`의 `open(..., "ab")` |
| CSV 파일이 실행 중에 지워짐 | `FileNotFoundError` | `storage.read_at()`, `scan()` |
| CSV 한 줄이 깨짐 (수동 편집, 쓰다가 비정상 종료) | `ValueError`, `IndexError` | `storage._decode()`에서 `int("abc")` 등 |
| B+ 트리의 offset이 실제 줄 시작이 아님 (인덱스와 파일 불일치) | `ValueError` 등 | `read_at()` 후 디코딩 |
| 엔진 버그 | `TypeError`, `KeyError` 등 | 예: `executor.py`의 "실행할 수 없는 AST" |

## 응답 구조

이 항목을 읽으면 성공과 실패 응답에 어떤 필드가 들어가는지 알 수 있어요.

모든 응답은 `Content-Type: application/json; charset=utf-8`이고, 바디의 `ok` 필드로 성공과 실패를 구분해요.

### 성공

SELECT는 200으로 응답해요.

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Content-Length: 106

{"ok": true, "type": "select", "columns": ["id", "name", "age"], "rows": [[3, "kim", 25]], "row_count": 1}
```

INSERT는 201로 응답해요.

```http
HTTP/1.1 201 Created
Content-Type: application/json; charset=utf-8
Content-Length: 68

{"ok": true, "type": "insert", "inserted_id": 4, "affected_rows": 1}
```

| 필드 | 의미 | 예시 |
| --- | --- | --- |
| `ok` | 성공 여부 | `true` |
| `type` | 실행한 문장 종류. `Result.type` | `"select"`, `"insert"` |
| `columns` | SELECT 결과의 컬럼 이름 목록. `Result.columns` | `["id", "name", "age"]` |
| `rows` | SELECT 결과의 행 목록. 각 행은 `columns`와 같은 순서의 값 목록. `Result.rows` | `[[3, "kim", 25]]` |
| `row_count` | SELECT가 반환한 행 수. `Result.affected` | `1` |
| `inserted_id` | INSERT로 자동 부여된 id. `Result.inserted_id` | `4` |
| `affected_rows` | INSERT로 삽입한 행 수. `Result.affected` | `1` |
| `used_index` | SELECT가 인덱스를 썼는지 여부. [디버깅용 필드](#디버깅용-필드) | `true` |
| `elapsed_ms` | 엔진 처리 시간(밀리초). SELECT와 INSERT 모두. [디버깅용 필드](#디버깅용-필드) | `0.31` |

위 응답 예시에서는 `used_index`와 `elapsed_ms`를 생략했어요.

### 실패

```http
HTTP/1.1 404 Not Found
Content-Type: application/json; charset=utf-8
Content-Length: 91

{"ok": false, "error": {"code": "TABLE_NOT_FOUND", "message": "없는 테이블 'orders'"}}
```

| 필드 | 의미 | 예시 |
| --- | --- | --- |
| `ok` | 성공 여부 | `false` |
| `error.code` | 실패 원인. [요청 검사](#요청-검사)와 [엔진 예외 변환](#엔진-예외-변환)의 `error.code` | `"TABLE_NOT_FOUND"` |
| `error.message` | 사람이 읽는 설명. 엔진 예외는 엔진 메시지를 그대로 써요 | `"없는 테이블 'orders'"` |

## 디버깅용 필드

이 항목을 읽으면 인덱스 사용 여부와 실행 시간을 응답에 넣기 위해 무엇을 바꾸는지 알 수 있어요.

### `elapsed_ms`

엔진이 SQL을 처리한 시간(밀리초)이에요. 엔진은 바꾸지 않고, 서버가 `execute()` 앞뒤로 시간을 재요.

```python
import time

start = time.perf_counter()
result = engine.execute(sql)
elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
```

### `used_index`, `type`, `inserted_id`

인덱스를 썼는지, 어떤 문장이었는지, 어떤 id를 부여했는지는 실행기만 알아요.
`Result`에 필드 세 개를 추가하고, `run_insert()`와 `run_select()`가 채워요.

```python
@dataclass
class Result:
    columns: List[str] = field(default_factory=list)
    rows: List[list] = field(default_factory=list)
    affected: int = 0
    type: str = ""                      # 추가: "insert" / "select"
    inserted_id: Optional[int] = None   # 추가
    used_index: bool = False            # 추가

def run_insert(self, ast: InsertStmt) -> Result:
    ...
    return Result(affected=1, type="insert", inserted_id=new_id)

def run_select(self, ast: SelectStmt) -> Result:
    names = [name for name, _ in self.schema[ast.table]]
    index = {name: i for i, name in enumerate(names)}
    used_index = self._is_id_lookup(ast.table, ast.where)   # 분기 결과를 변수로
    if used_index:
        ...
    else:
        ...
    return Result(columns=columns, rows=rows, affected=len(rows),
                  type="select", used_index=used_index)
```

| 필드 | 의미 | 예시 |
| --- | --- | --- |
| `type` | 실행한 문장 종류. 서버가 200과 201을 고를 때 써요 | `"select"` |
| `inserted_id` | INSERT로 자동 부여된 id. SELECT는 `None` | `4` |
| `used_index` | SELECT가 B+ 트리 인덱스로 행을 읽었는지 여부. INSERT는 `False` | `true` |

새 필드에는 모두 기본값이 있어서, `Result`를 쓰는 CLI와 기존 코드는 바꾸지 않아도 돼요.
