# AST 구조

이 문서를 읽으면 파서가 만드는 AST 노드의 필드와, 파서가 어떤 노드를 만들지 고르는 방법을 알 수 있어요.

## 노드

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

## 예시

```
INSERT INTO users VALUES (1, 'kim', 25)
→ InsertStmt { table: "users", values: [1, "kim", 25] }

SELECT * FROM users
→ SelectStmt { table: "users", columns: 없음, where: 없음 }

SELECT name FROM users WHERE age >= 20
→ SelectStmt { table: "users", columns: ["name"],
               where: Condition { column: "age", op: >=, value: 20 } }
```

## 파서가 노드를 고르는 방법

파서는 첫 토큰을 보고 만들 노드를 한 번 고르고, 고른 함수가 [문법](grammar.md) 순서대로 토큰을 읽으며 필드를 채워요.

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

파서가 완성한 AST는 검증 단계에서 스키마와 비교한 뒤 [실행기](executor.md)로 넘어가요.
