# Phase 1 설계

이 문서를 읽으면 SQL 파일 하나가 CLI에서 CSV 파일까지 어떤 단계를 거쳐 처리되는지, 각 단계를 어떻게 설계했는지 알 수 있어요.

## 처리 흐름

```
CLI ──→ 토크나이저 ──→ 파서 ──→ 검증 ──→ 실행기 ──→ Result ──→ CLI 출력
 │        토큰 목록       AST      AST        │
 │                                            ↓
 │                                         저장 계층 ──→ users.csv
 └─ SQL 파일을 읽고 ; 기준으로 문장을 나눠요
```

- CLI는 문장마다 `engine.execute(stmt)`를 호출해요.
- `execute()`는 토크나이저, 파서, 검증, 실행기를 순서대로 호출하고 `Result`를 반환해요.
- 실행기만 저장 계층을 호출하고, 파일은 저장 계층만 열어요.

## 목차

1. [CLI](#cli)
2. [토큰 기준](#토큰-기준)
3. [문법](#문법)
4. [AST 구조](#ast-구조)
5. [실행기](#실행기)
6. [저장 계층](#저장-계층)
7. [에러 처리](#에러-처리)

## CLI

이 항목을 읽으면 CLI가 SQL 파일을 문장으로 나누고, 문장을 하나씩 실행하는 방법을 알 수 있어요.
인자와 파일 검사는 [에러 처리](#cli-에러)에서 다뤄요.

### 문장 분리

`split_statements(sql)`은 파일 내용 전체를 받아 `;` 기준으로 문장 목록을 만들어요.

- 따옴표 안에 있는지 기억해서, 문자열 안의 `;`에서는 자르지 않아요.
- 빈 문장(`;;`)과 닫히지 않은 따옴표는 에러를 내지 않고 그대로 넘겨요. 에러는 파서와 토크나이저가 내요.
- 마지막 `;`가 없어도 남은 내용을 마지막 문장으로 넣어요.

```python
def split_statements(sql):
    stmts, buf, in_quote = [], [], False
    for ch in sql:
        if ch == "'":
            in_quote = not in_quote
        if ch == ";" and not in_quote:
            stmts.append("".join(buf))   # 빈 문장도 그대로 전달
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        stmts.append("".join(buf))       # 따옴표가 안 닫혔어도 그대로 전달
    return stmts
```

예시:

```
입력: "INSERT INTO memo VALUES (1, 'a;b'); SELECT * FROM memo"

I N S E R T ... ( 1 ,   '     a   ;   b   '     )   ;     S E L E C T ...
                        ↑         ↑       ↑         ↑
                    따옴표 안   무시됨  따옴표 밖  여기서 자름

결과: ["INSERT INTO memo VALUES (1, 'a;b')", " SELECT * FROM memo"]
```

### 문장 실행

`split_statements()`가 목록을 다 만든 뒤, CLI가 문장을 하나씩 엔진에 넘겨요.
`execute()`는 일반 함수 호출이라, 앞 문장이 끝나야 다음 문장이 실행돼요.

```
sql = 파일 내용

stmts = split_statements(sql)      ① 나누기만 하고 끝나요
                                      → ["INSERT ...", "SELECT ...", "INSERT ..."]

for stmt in stmts:                 ② 완성된 목록을 하나씩 실행해요
    result = engine.execute(stmt)
    print_table(result)
```

실행기는 출력하지 않고 [Result](#결과-형식)를 반환해요. 화면에 표로 출력하는 건 CLI의 일이에요.

## 토큰 기준

이 항목을 읽으면 토크나이저가 문장을 어떤 종류의 토큰으로 자르는지 알 수 있어요.
토크나이저가 내는 에러는 [에러 처리](#토크나이저-에러)에서 다뤄요.

### 토큰 종류

| 종류 | 의미 | 형식 | 예시 |
| --- | --- | --- | --- |
| 키워드 | SQL 문법 단어 | `INSERT` `INTO` `VALUES` `SELECT` `FROM` `WHERE`. 대소문자를 구분하지 않아요 | `SELECT`, `select` |
| 식별자 | 테이블 이름, 컬럼 이름 | 영문자나 `_`로 시작하고 영문자, 숫자, `_`로 이어져요 | `users`, `name` |
| 숫자 | 정수 값 | 숫자만. `-` 바로 뒤에 숫자가 오면 음수 하나로 읽어요 | `25`, `-5` |
| 문자열 | 문자열 값 | 작은따옴표로 감싸요. 안의 공백, 쉼표, `;`도 문자열이에요 | `'kim'` |
| 기호 | 괄호, 구분자, 연산자 | `(` `)` `,` `*` `=` `!=` `<` `>` `<=` `>=` | `>=` |
| EOF | 문장의 끝 | 토큰 목록 맨 끝에 하나 붙여요 | |

`;`는 토큰이 아니에요. [CLI](#문장-분리)가 문장을 나누면서 이미 제거해요.

### 자르는 규칙

문자를 하나씩 읽으면서, 첫 글자를 보고 토큰 종류를 정해요.

1. 공백, 탭, 줄바꿈은 건너뛰어요. 줄 번호는 세어서 토큰에 기록해요.
2. 영문자나 `_`로 시작하면 단어를 끝까지 읽어요. 대문자로 바꾼 단어가 키워드 목록에 있으면 키워드, 없으면 식별자예요.
3. 숫자로 시작하거나 `-` 바로 뒤에 숫자가 오면 숫자 토큰이에요.
4. `'`로 시작하면 다음 `'`까지 문자열 토큰이에요.
5. `!=`, `<=`, `>=`를 먼저 확인하고, 아니면 한 글자 기호를 확인해요.
6. 그 외의 문자는 에러예요.

공백은 토큰을 나누는 유일한 기준이 아니에요. `id=5`도 `id`, `=`, `5` 세 토큰이에요.

### 대소문자

| 대상 | 규칙 | 예시 |
| --- | --- | --- |
| 키워드 | 구분하지 않아요 | `select`와 `SELECT`는 같아요 |
| 문자열 값 | 구분해요 | `'Kim'`과 `'kim'`은 달라요 |

키워드는 테이블 이름이나 컬럼 이름으로 쓸 수 없어요. `select`라는 테이블은 키워드로 읽혀요.

### 예시

```
INSERT INTO users VALUES (1, 'kim')

→ [INSERT, INTO, IDENT(users), VALUES, LPAREN, NUMBER(1), COMMA, STRING(kim), RPAREN, EOF]
```

## 문법

이 항목을 읽으면 처리기가 받아들이는 INSERT 문과 SELECT 문의 형식을 알 수 있어요.
형식에 맞지 않는 문장은 파서가 에러로 처리해요. 에러는 [에러 처리](#파서-에러)에서 다뤄요.

### 표기법

| 기호 | 뜻 |
| --- | --- |
| `<이름>` | 그 자리에 들어갈 요소. 아래 "요소" 표에서 설명해요 |
| `[ ... ]` | 생략할 수 있어요 |
| `( ... )*` | 0번 이상 반복해요 |
| `a \| b` | a 또는 b 중 하나예요 |
| 대문자 단어 | 키워드. 대소문자를 구분하지 않아요 |

### 문법 규칙

```
INSERT 문 = INSERT INTO <테이블> VALUES ( <값> ( , <값> )* )
SELECT 문 = SELECT <컬럼 목록> FROM <테이블> [ WHERE <조건> ]

<컬럼 목록> = * | <컬럼> ( , <컬럼> )*
<조건>      = <컬럼> <연산자> <값>
<연산자>    = = | != | < | > | <= | >=
<값>        = <숫자> | <문자열>
```

### 요소

| 요소 | 의미 | 형식 | 예시 |
| --- | --- | --- | --- |
| `<테이블>` | 데이터를 넣거나 읽을 테이블 | 영문자나 `_`로 시작하고 영문자, 숫자, `_`로 이어지는 이름. 키워드는 쓸 수 없어요 | `users` |
| `<컬럼>` | 테이블의 컬럼 | `<테이블>`과 같아요 | `name` |
| `<숫자>` | 정수 값 | 숫자만, 음수는 `-`를 붙여요. 소수는 지원하지 않아요 | `25`, `-5` |
| `<문자열>` | 문자열 값 | 작은따옴표로 감싸요. 안의 `'`는 `''`로 써요 | `'kim'`, `'it''s'` |
| `<연산자>` | WHERE에서 값을 비교하는 방법 | 위 6개 중 하나 | `>=` |

### 지원하지 않는 것

- INSERT에서 컬럼 목록 지정: `INSERT INTO users (name) VALUES ('kim')`
- WHERE에서 조건 여러 개: `AND`, `OR`
- `ORDER BY`, `LIMIT`, `COUNT`, 산술 연산(`age + 1`)

### 예시

| 문장 | AST |
| --- | --- |
| `INSERT INTO users VALUES (1, 'kim', 25)` | `InsertStmt { table: "users", values: [1, "kim", 25] }` |
| `SELECT * FROM users` | `SelectStmt { table: "users", columns: 없음, where: 없음 }` |
| `SELECT name FROM users WHERE age >= 20` | `SelectStmt { table: "users", columns: ["name"], where: Condition { "age", >=, 20 } }` |

AST의 필드는 [AST 구조](#ast-구조)에서 다뤄요.

## AST 구조

이 항목을 읽으면 파서가 만드는 AST 노드의 필드와, 파서가 어떤 노드를 만들지 고르는 방법을 알 수 있어요.

### 노드

```
InsertStmt
  table   : 문자열           -- 예: "users"
  values  : 값 목록          -- 예: [1, "kim", 25]

SelectStmt
  table   : 문자열           -- 예: "users"
  columns : 컬럼 이름 목록    -- 예: ["name", "age"],  SELECT * 이면 없음(None)
  where   : Condition        -- WHERE가 없으면 없음(None)

Condition
  column  : 문자열           -- 예: "age"
  op      : 연산자           -- =, !=, <, >, <=, >= 중 하나
  value   : 값               -- 예: 20

값 = 숫자 또는 문자열        -- 숫자 토큰은 숫자로, 문자열 토큰은 따옴표를 뗀 문자열로
```

- `SELECT *`는 `columns`를 없음(None)으로 둬요. `"*"`라는 이름의 컬럼과 헷갈리지 않게 하려는 거예요.
- 키워드, 괄호, 쉼표, EOF 토큰은 AST에 남지 않아요. 파서가 순서를 확인하는 데만 써요.

### 예시

```
INSERT INTO users VALUES (1, 'kim', 25)
→ InsertStmt { table: "users", values: [1, "kim", 25] }

SELECT * FROM users
→ SelectStmt { table: "users", columns: 없음, where: 없음 }

SELECT name FROM users WHERE age >= 20
→ SelectStmt { table: "users", columns: ["name"],
               where: Condition { column: "age", op: >=, value: 20 } }
```

### 파서가 노드를 고르는 방법

파서는 첫 토큰을 보고 만들 노드를 한 번 고르고, 고른 함수가 [문법](#문법) 순서대로 토큰을 읽으며 필드를 채워요.

```
parse(tokens):
    첫 토큰이 INSERT → parse_insert() → InsertStmt
    첫 토큰이 SELECT → parse_select() → SelectStmt
    그 외             → 에러: "문장은 INSERT 또는 SELECT로 시작해야 함"

parse_select():
    SELECT 확인
    columns ← * 이면 없음, 아니면 컬럼 이름 목록
    FROM 확인
    table   ← 식별자
    다음 토큰이 WHERE 이면 where ← parse_condition(), 아니면 없음
    EOF 확인
    return SelectStmt(table, columns, where)
```

파서가 완성한 AST는 검증 단계에서 스키마와 비교한 뒤 [실행기](#실행기)로 넘어가요.

## 실행기

이 항목을 읽으면 실행기가 AST를 받아 어떤 순서로 실행하고, 어떤 형식으로 결과를 반환하는지 알 수 있어요.

### 구조

실행기는 AST의 종류로 실행 함수를 고르고, 파일은 [저장 계층](#저장-계층)을 거쳐서만 다뤄요.

```
class Executor:
    run(ast):                 # 분기만 담당
        InsertStmt → run_insert(ast)
        SelectStmt → run_select(ast)

    run_insert(ast):          # INSERT의 실행 순서
        1. ast.values를 스키마의 컬럼 순서에 맞춰 레코드로 만든다
        2. offset ← storage.append(ast.table, 레코드)
        3. index.insert(id, offset)                       -- Phase 2
        4. Result를 반환한다

    run_select(ast):          # SELECT의 실행 순서
        1. 행 읽기: where가 id 조건이면 인덱스, 아니면 storage.scan(ast.table)  -- 인덱스는 Phase 2
        2. 거르기: _match()로 조건에 맞는 행만 남긴다
        3. 컬럼 고르기: _project()로 필요한 컬럼만 남긴다
        4. Result를 반환한다
```

명령어를 추가할 때는 `run()`에 분기를 하나 넣고 `run_update()` 같은 함수를 만들어요.

### 도우미 함수

두 함수 모두 컬럼 이름을 행 안의 위치로 바꿔야 해요. 실행기는 스키마로 `{"id": 0, "name": 1, "age": 2}` 같은 표를 만들어 함께 써요.

#### `_match(row, condition)`

행 하나를 남길지 판단해요.

```
_match(row, condition):
    condition이 없으면 → True              -- WHERE가 없으면 모든 행을 남김
    값 ← row에서 condition.column 위치의 값
    값 condition.op condition.value 를 비교한 결과를 반환

예) 스키마: [id, name, age]
_match([1, "kim", 25], Condition("age", >=, 20))  → 25 >= 20 → True
_match([2, "lee", 17], Condition("age", >=, 20))  → 17 >= 20 → False
```

#### `_project(row, columns)`

행에서 필요한 컬럼만 골라요.

```
_project(row, columns):
    columns가 없으면(SELECT *) → row 전체
    아니면 → columns 순서대로 각 컬럼 위치의 값만 모아 반환

예) 스키마: [id, name, age]
_project([1, "kim", 25], ["name", "age"])  → ["kim", 25]
_project([1, "kim", 25], ["age", "name"])  → [25, "kim"]     -- 적힌 순서대로
_project([1, "kim", 25], None)             → [1, "kim", 25]
```

### 결과 형식

실행기는 어떤 문장이든 같은 형식의 `Result`를 반환해요.

| 필드 | 의미 | 예시 |
| --- | --- | --- |
| `columns` | 컬럼 이름 목록. INSERT는 빈 목록이에요 | `["name", "age"]` |
| `rows` | 행 목록. 각 행은 `columns`와 같은 순서의 값 목록이에요. INSERT는 빈 목록이에요 | `[["kim", 25]]` |
| `affected` | INSERT는 삽입한 행 수, SELECT는 반환한 행 수예요 | `1` |

```
INSERT INTO users VALUES (6, 'yoon', 28)
→ Result { columns: [], rows: [], affected: 1 }

SELECT name, age FROM users WHERE age >= 20
→ Result { columns: ["name", "age"],
           rows: [["kim", 25], ["park", 31], ["han", 22]],
           affected: 3 }

SELECT * FROM users WHERE age > 100      -- 결과 0행
→ Result { columns: ["id", "name", "age"], rows: [], affected: 0 }
```

- 결과가 0행이어도 에러가 아니에요. 컬럼 이름은 그대로 들어가요.
- 에러는 `Result`에 담지 않고 예외로 알려요. CLI가 예외를 잡아 출력해요.

## 저장 계층

이 항목을 읽으면 저장 계층이 CSV 파일에 행을 쓰고 읽는 방법과, 각 함수가 언제 쓰이는지 알 수 있어요.
CSV를 고른 이유는 [ADR 0001](../adr/0001-storage-format.md)에서 다뤄요.

### `Storage` 클래스

파일을 열고 읽고 쓰는 코드는 모두 이 클래스 안에 있어요. 실행기는 이 클래스의 함수만 호출해요.

```python
class Storage:
    def __init__(self, data_dir):
        self.data_dir = data_dir

    def append(self, table, record) -> int:
        """레코드를 파일 끝에 추가하고, 그 행의 시작 오프셋을 반환"""
        with open(self._path(table), "ab") as f:
            offset = f.tell()
            f.write(self._encode(record))
            return offset

    def scan(self, table):
        """모든 행을 (오프셋, 레코드) 쌍으로 하나씩 반환. 선형 탐색과 인덱스 재구축에 사용"""

    def read_at(self, table, offset):
        """오프셋 위치의 행 하나만 읽기. Phase 2 인덱스 조회에 사용"""

    def _encode(self, record) -> bytes: ...   # 레코드 → CSV 한 줄
    def _decode(self, line) -> list: ...      # CSV 한 줄 → 레코드
```

| 함수 | 쓰는 곳 | 반환 |
| --- | --- | --- |
| `append(table, record)` | INSERT | 새 행의 시작 바이트 오프셋. 쓰기 직전의 `tell()` 값이에요 (예: `18`) |
| `scan(table)` | WHERE가 id 조건이 아닌 SELECT, 인덱스 재구축 | `(오프셋, 레코드)`를 한 행씩 넘기는 제너레이터 |
| `read_at(table, offset)` | Phase 2의 `WHERE id = ?` | 그 위치의 레코드 하나 |

- 파일은 바이너리 모드(`"ab"`, `"rb"`)로 열어요. 텍스트 모드에서는 `tell()` 값이 실제 바이트 위치와 다를 수 있어요.
- `scan()`은 배열 대신 한 행씩 넘겨요. 100만 행을 한 번에 메모리에 올리지 않으려는 거예요.

### CSV 변환

`_encode`는 파일에 쓰기 직전에, `_decode`는 파일에서 한 줄을 읽은 직후에 쓰여요.

```
INSERT INTO users VALUES (3, 'park', 28)
→ 실행기: storage.append("users", [3, "park", 28])
   → append 안에서: _encode([3, "park", 28]) → b"3,park,28\n"
   → 그 바이트를 파일 끝에 씀

SELECT * FROM users
→ 실행기: storage.scan("users")
   → scan 안에서: 한 줄 읽기 b"3,park,28\n"
   → _decode(b"3,park,28\n") → [3, "park", 28]
   → 실행기에게 넘겨줌
```

- 값에 쉼표나 큰따옴표가 있으면 표준 라이브러리 `csv` 모듈의 규칙대로 큰따옴표로 감싸요. (예: `2,"a,b",30`)
- CSV에는 타입이 없어서 읽으면 모든 값이 문자열이에요. `_decode`는 스키마의 컬럼 타입을 보고 숫자 컬럼을 `int`로 바꿔요.

## 에러 처리

이 항목을 읽으면 각 단계가 어떤 에러를 잡는지, 에러가 나면 사용자에게 무엇을 보여주는지 알 수 있어요.

### 단계별 책임

| 단계 | 잡는 에러 | 기준 |
| --- | --- | --- |
| CLI | 인자, 파일 | SQL 내용을 보기 전에 알 수 있는 문제 |
| 토크나이저 | 토큰 하나를 만들 수 없음 | 토큰을 만드는 도중에 생긴 문제 |
| 파서 | 토큰의 순서나 조합이 틀림 | 토큰은 멀쩡한데 문법에 맞지 않는 문제 |
| 검증 | 스키마와 맞지 않음 | 문법은 맞는데 실제 테이블과 맞지 않는 문제 |

### CLI 에러

에러를 stderr에 출력하고 종료 코드 1로 종료해요.

| 에러 | 예시 |
| --- | --- |
| 인자 개수가 맞지 않음 | `./mini-dbms`, `./mini-dbms a.sql b.sql` |
| 파일이 없음 | `./mini-dbms nofile.sql` |
| 파일을 읽을 수 없음 | 권한 없음, UTF-8이 아닌 인코딩 |
| 빈 파일 | 내용이 없거나 공백만 있음 |

빈 문장(`;;`)과 닫히지 않은 따옴표는 CLI가 잡지 않고 그대로 넘겨요. [CLI](#문장-분리)를 봐요.

### 토크나이저 에러

에러 메시지에 행과 열을 함께 써요.

| 에러 | 예시 | 메시지 예시 |
| --- | --- | --- |
| 모르는 문자 | `@`, `#`, `$`, `"` | `알 수 없는 문자 '@' (2행 15열)` |
| `!` 단독 사용 | `id ! 5`, `id !5` | `'!' 뒤에는 '='가 와야 함` |
| 닫히지 않은 문자열 | `'kim` | `닫히지 않은 문자열 (3행에서 시작)` |
| `-` 뒤에 숫자가 없음 | `- 5`, `-abc`, `-` | `'-' 뒤에는 숫자가 와야 함` |
| 숫자 바로 뒤에 문자 | `12abc`, `5name` | `잘못된 숫자 '12abc'` |
| 소수점 | `3.14` | `.`가 모르는 문자로 걸려요 |

키워드 오타(`VALUE`, `SELEC`)는 토크나이저에게 정상적인 식별자예요. 파서가 잡아요.

### 파서 에러

형식이 맞지 않으면 기대한 토큰, 실제로 온 토큰, 위치를 포함한 에러를 내고 AST를 반환하지 않아요.

| 에러 | 예시 | 메시지 예시 |
| --- | --- | --- |
| 키워드 오타 | `INSERT INTO users VALUE (1)` | `VALUES가 필요한데 'value'가 옴` |
| 시작 키워드가 아님 | `SELEC * FROM users` | `문장은 INSERT 또는 SELECT로 시작해야 함` |
| 키워드 누락 | `INSERT users VALUES (1)`, `SELECT * users` | `INTO가 필요한데 'users'가 옴` |
| 괄호 짝 불일치 | `INSERT INTO users VALUES (1, 2` | `')'가 필요한데 EOF가 옴` |
| 쉼표 누락, 끝 쉼표 | `VALUES (1 2)`, `VALUES (1,)`, `SELECT name,` | `','나 ')'가 필요한데 '2'가 옴` |
| 값 자리에 식별자 | `VALUES (kim)`, `WHERE age = name` | `값이 필요한데 'name'이 옴` |
| 연산자 누락 | `SELECT * FROM users WHERE age` | `연산자가 필요한데 EOF가 옴` |
| 남은 토큰 | `SELECT * FROM users abc` | `문장 끝이어야 하는데 'abc'가 옴` |
| 빈 문장 | `;;` 사이의 빈 문장 | `빈 문장` |

### 검증 에러

검증은 파서와 실행기 사이에서 해요. 통과한 AST만 실행기로 넘어가서, 잘못된 데이터가 파일에 쓰이지 않아요.

| 에러 | 예시 |
| --- | --- |
| 없는 테이블 | `SELECT * FROM nope` |
| 없는 컬럼 | `SELECT nope FROM users`, `WHERE nope = 1` |
| 값 개수가 컬럼 수와 다름 | 컬럼이 3개인데 `VALUES (1, 'kim')` |
| 값 타입이 컬럼 타입과 다름 | 숫자 컬럼에 `'abc'` |
