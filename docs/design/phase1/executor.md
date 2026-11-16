# 실행기

이 문서를 읽으면 실행기가 AST를 받아 어떤 순서로 실행하고, 어떤 형식으로 결과를 반환하는지 알 수 있어요.

## 구조

실행기는 AST의 종류로 실행 함수를 고르고, 파일은 [저장 계층](storage.md)을 거쳐서만 다뤄요.

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

## 도우미 함수

두 함수 모두 컬럼 이름을 행 안의 위치로 바꿔야 해요. 실행기는 스키마로 `{"id": 0, "name": 1, "age": 2}` 같은 표를 만들어 함께 써요.

### `_match(row, condition)`

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

### `_project(row, columns)`

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

## 결과 형식

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
