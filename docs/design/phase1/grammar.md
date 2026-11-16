# 문법

이 문서를 읽으면 처리기가 받아들이는 INSERT 문과 SELECT 문의 형식을 알 수 있어요.
형식에 맞지 않는 문장은 파서가 에러로 처리해요. 에러는 [에러 처리](errors.md#파서)에서 다뤄요.

## 표기법

| 기호 | 뜻 |
| --- | --- |
| `<이름>` | 그 자리에 들어갈 요소. 아래 "요소" 표에서 설명해요 |
| `[ ... ]` | 생략할 수 있어요 |
| `( ... )*` | 0번 이상 반복해요 |
| `a \| b` | a 또는 b 중 하나예요 |
| 대문자 단어 | 키워드. 대소문자를 구분하지 않아요 |

## 문법 규칙

```
INSERT 문 = INSERT INTO <테이블> VALUES ( <값> ( , <값> )* )
SELECT 문 = SELECT <컬럼 목록> FROM <테이블> [ WHERE <조건> ]

<컬럼 목록> = * | <컬럼> ( , <컬럼> )*
<조건>      = <컬럼> <연산자> <값>
<연산자>    = = | != | < | > | <= | >=
<값>        = <숫자> | <문자열>
```

## 요소

| 요소 | 의미 | 형식 | 예시 |
| --- | --- | --- | --- |
| `<테이블>` | 데이터를 넣거나 읽을 테이블 | 영문자나 `_`로 시작하고 영문자, 숫자, `_`로 이어지는 이름. 키워드는 쓸 수 없어요 | `users` |
| `<컬럼>` | 테이블의 컬럼 | `<테이블>`과 같아요 | `name` |
| `<숫자>` | 정수 값 | 숫자만, 음수는 `-`를 붙여요. 소수는 지원하지 않아요 | `25`, `-5` |
| `<문자열>` | 문자열 값 | 작은따옴표로 감싸요. 안의 `'`는 `''`로 써요 | `'kim'`, `'it''s'` |
| `<연산자>` | WHERE에서 값을 비교하는 방법 | 위 6개 중 하나 | `>=` |

## 지원하지 않는 것

- INSERT에서 컬럼 목록 지정: `INSERT INTO users (name) VALUES ('kim')`
- WHERE에서 조건 여러 개: `AND`, `OR`
- `ORDER BY`, `LIMIT`, `COUNT`, 산술 연산(`age + 1`)

## 예시

| 문장 | AST |
| --- | --- |
| `INSERT INTO users VALUES (1, 'kim', 25)` | `InsertStmt { table: "users", values: [1, "kim", 25] }` |
| `SELECT * FROM users` | `SelectStmt { table: "users", columns: 없음, where: 없음 }` |
| `SELECT name FROM users WHERE age >= 20` | `SelectStmt { table: "users", columns: ["name"], where: Condition { "age", >=, 20 } }` |

AST의 필드는 [AST 구조](ast.md)에서 다뤄요.
