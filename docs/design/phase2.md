# Phase 2 설계

이 문서를 읽으면 실행기가 B+ 트리 인덱스를 어떻게 들고 있다가 INSERT와 SELECT에 쓰는지, B+ 트리가 어떤 규칙으로 동작하는지 알 수 있어요.
Phase 1의 처리 흐름과 저장 계층은 [Phase 1 설계](phase1.md)를 따라요.

## 목차

1. [실행기](#실행기)
2. [B+ 트리](#b-트리)

## 실행기

이 항목을 읽으면 실행기가 테이블마다 인덱스를 어떻게 관리하고, INSERT와 SELECT에서 인덱스를 언제 쓰는지 알 수 있어요.

### 필드

```python
class Executor:
    def __init__(self, storage, schema):
        self.storage = storage
        self.schema = schema
        self.indexes = {}   # 테이블 → BPlusTree
        self.next_id = {}   # 테이블 → 다음에 줄 id
        for table in schema:
            self._load(table)
```

| 필드 | 의미 | 예시 |
| --- | --- | --- |
| `storage` | 파일을 읽고 쓰는 [저장 계층](phase1.md#저장-계층) | `Storage("data")` |
| `schema` | 테이블별 컬럼 이름과 타입 | `{"users": [("id", int), ("name", str), ("age", int)]}` |
| `indexes` | 테이블 이름 → 그 테이블의 `BPlusTree` | `{"users": BPlusTree(...)}` |
| `next_id` | 테이블 이름 → 다음 INSERT에 부여할 id | `{"users": 6}` |

생성할 때 스키마의 테이블마다 `_load(table)`을 호출해서 `indexes`와 `next_id`를 채워요.

### INSERT

`run_insert(ast)`는 아래 순서로 동작해요.

```
run_insert(ast):
    1. id 자동 부여
    2. id를 포함한 레코드 구성
    3. 파일에 쓰고 offset 받기
    4. B+ 트리에 (id, offset) 삽입
    5. 다음 id 준비
```

### SELECT

`run_select(ast)`는 WHERE가 `id = ?`이면 인덱스로, 그 외에는 선형 탐색으로 행을 읽어요.

```python
def run_select(self, ast):
    names = [name for name, _ in self.schema[ast.table]]
    column_index = {name: i for i, name in enumerate(names)}

    if self._is_id_lookup(ast.where):                       # WHERE id = ?
        offset = self.indexes[ast.table].search(ast.where.value)
        records = [] if offset is None else [self.storage.read_at(ast.table, offset)]
    else:                                                   # 그 외 → 선형 탐색
        records = (rec for _, rec in self.storage.scan(ast.table))

    rows = [self._project(r, ast.columns, index)
            for r in records if self._match(r, ast.where, column_index)]
    ...
```

| 경우 | 행을 읽는 방법 |
| --- | --- |
| `WHERE id = ?` | 인덱스에서 offset을 찾고 `storage.read_at()`으로 한 행만 읽어요. offset이 없으면 결과는 0행이에요 |
| 그 외 | `storage.scan()`으로 모든 행을 읽어요 |

어느 경우든 읽은 행은 [`_match()`](phase1.md#_matchrow-condition)로 거르고 [`_project()`](phase1.md#_projectrow-columns)로 컬럼을 골라요.

## B+ 트리

이 항목을 읽으면 B+ 트리가 지켜야 하는 규칙과, 노드 크기를 어떻게 정하는지 알 수 있어요.

### 구조 규칙

1. 노드는 정렬된 키를 최대 키 개수(`MAX_KEYS`)까지 가진다.
2. 내부 노드는 자식 수 = 키 수 + 1이다.
3. 실제 데이터 `(id, offset)`는 리프에만 있고, 내부 노드의 키는 이정표다.
4. 모든 리프는 같은 깊이에 있다.

### 검색 규칙

5. 루트에서 리프까지 내려간다. 각 내부 노드에서 `children[bisect_right(keys, key)]`로 자식을 고른다.
6. 리프에서 키를 찾으면 offset을, 없으면 `None`을 반환한다.

### 삽입 규칙

7. 삽입은 항상 리프에서 일어나고, 정렬된 위치에 넣는다.
8. 넘치지 않으면 끝이다.
9. 리프가 넘치면 반으로 나누고, 오른쪽 첫 키를 부모로 복사한다.
10. 내부 노드가 넘치면 가운데 키를 부모로 이동한다.
11. 루트가 넘치면 새 루트를 만들고, 높이가 1 늘어난다.

### 정한 것

| 대상 | 정한 내용 |
| --- | --- |
| 가운데 키 | 키 개수가 짝수라 가운데가 둘이면 오른쪽 가운데 키를 써요 |
| 자식 고르기 | 검색할 때 `bisect_right`를 써요 |
| `MAX_KEYS` | 생성자 인자로 받아요. 기본값은 `64`이고, 테스트에서는 분할이 자주 일어나도록 `3`~`4`처럼 작게 써요 |
