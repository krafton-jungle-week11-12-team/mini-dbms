# Phase 2 테스트 케이스

이 문서를 읽으면 Phase 2의 id 자동 부여, 인덱스 복구, 인덱스 조회, B+ 트리 분할과 검색을 어떤 입력으로 테스트하고, 어떤 결과를 기대하는지 알 수 있어요.
기대 결과는 [Phase 2 설계](../design/phase2.md)와 [Phase 2 요구사항](../requirements/phase2.md)을 따라요.

## 작성 방식

- [Phase 1 테스트 케이스](phase1.md#작성-방식)와 같은 방식으로 써요. 표 하나가 테스트 함수 하나이고, 각 행은 `pytest.mark.parametrize`의 케이스 한 줄이에요.
- ID는 Phase 1 번호에 이어서 붙여요. B+ 트리는 `T-BPT-01`부터 시작해요.
- 스키마는 Phase 1과 같은 `users(id INT, name TEXT, age INT)`예요. Phase 2에서는 id를 실행기가 부여하므로, `InsertStmt`의 `values`에는 id를 빼고 `name`, `age`만 넣어요.
- 실행기 테스트에서 "재시작"은 준비한 `users.csv`로 `Executor`를 새로 만드는 것을 뜻해요.
- B+ 트리 테스트는 `BPlusTree(max_keys=3)`로 분할이 자주 일어나게 해요. 값은 키를 알아보기 쉽게 `insert(k, k * 10)`으로 넣어요.
- 분할 결과의 기대값은 설계 문서의 [정한 것](../design/phase2.md#정한-것)에 따라, 가운데 키가 둘이면 오른쪽 가운데 키를 쓰는 기준이에요.

## 검증

### `test_validate_error`: INSERT 값 개수와 타입

Phase 2에서는 INSERT 값에 id를 쓰지 않아요. 그래서 값 개수는 id를 뺀 컬럼 수(`name`, `age` 2개)와 비교하고, 값 타입도 id를 뺀 컬럼과 순서대로 맞춰 봐요.
Phase 1의 같은 함수에 케이스를 더해요.

| ID | 시나리오 | 입력 | 기대 에러 메시지 |
| --- | --- | --- | --- |
| T-VAL-05 | 값 개수 부족 | `INSERT INTO users VALUES ('kim')` | `값 개수가 컬럼 수와 다름` |
| T-VAL-06 | id까지 넣음 | `INSERT INTO users VALUES (1, 'kim', 23)` | `값 개수가 컬럼 수와 다름` |
| T-VAL-07 | 값 타입 다름 | `INSERT INTO users VALUES ('kim', 'abc')` | `컬럼 'age'의 타입과 맞지 않음` |

T-VAL-06은 Phase 1 방식으로 id를 직접 넣으면 막히는지 확인해요.

## 실행기

### `test_auto_id`: id 자동 부여와 `next_id` 복구

| ID | 시나리오 | 준비 (users.csv) | 실행 | 기대 결과 |
| --- | --- | --- | --- | --- |
| T-EXE-11 | id 자동 부여 | 빈 파일 | `run(InsertStmt { table: "users", values: ["kim", 23] })` 후 `run(InsertStmt { table: "users", values: ["lee", 30] })`, 그다음 `SELECT *` | `rows: [[1, "kim", 23], [2, "lee", 30]]` |
| T-EXE-12 | 재시작 후 `next_id` 복구 | `1,kim,23\n` | `run(InsertStmt { table: "users", values: ["lee", 30] })` 후 `SELECT *` | `rows: [[1, "kim", 23], [2, "lee", 30]]` (id 1과 겹치지 않음) |
| T-EXE-13 | 마지막 행이 최대 id가 아님 | `5,kim,23\n2,lee,30\n` | `run(InsertStmt { table: "users", values: ["park", 40] })` | 파일 내용 `5,kim,23\n2,lee,30\n6,park,40\n` (`next_id = 최대 id + 1`) |

### `test_index_recovery`: 재시작 후 인덱스 복구

| ID | 시나리오 | 준비 (users.csv) | 실행 | 기대 결과 |
| --- | --- | --- | --- | --- |
| T-EXE-14 | 인덱스 트리 복구 | `1,kim,23\n2,lee,30\n` | `Executor` 생성 후 `indexes["users"].search(2)` | `9` (id 2 행의 offset) |

### `test_select_by_index`: `WHERE id = ?` 인덱스 조회

`WHERE id = ?`는 결과만으로는 인덱스를 썼는지 알 수 없어요. 그래서 이 표의 케이스는 `storage.scan`을 호출하면 실패하도록 바꿔 두고 실행해요. 선형 탐색으로 빠지면 테스트가 실패해요.

| ID | 시나리오 | 준비 (users.csv) | 실행 | 기대 결과 |
| --- | --- | --- | --- | --- |
| T-EXE-15 | 인덱스로 한 행 조회 | `1,kim,23\n2,lee,30\n` | `run(SelectStmt { table: "users", columns: 없음, where: Condition { "id", =, 2 } })` | `rows: [[2, "lee", 30]], affected: 1` |
| T-EXE-16 | 인덱스에 없는 id | `1,kim,23\n` | `run(SelectStmt { table: "users", columns: 없음, where: Condition { "id", =, 99 } })` | `rows: [], affected: 0` |

## 저장 계층

Phase 2에서 쓰는 저장 계층 기능(`STO-01`~`STO-03`)은 Phase 1에서 이미 테스트해요. 여기서는 다시 쓰지 않아요.

| 요구사항 | 확인하는 Phase 1 케이스 |
| --- | --- |
| `STO-01` append 시 offset 반환 | [T-STO-01 ~ T-STO-03](phase1.md#test_storage-storage) |
| `STO-02` scan 시 offset 함께 반환 | [T-STO-05](phase1.md#test_storage-storage) |
| `STO-03` offset 위치의 행 읽기 | [T-STO-07](phase1.md#test_storage-storage) |

## B+ 트리

### `test_split`: 분할 후 트리 구조

노드 필드(`keys`, `children`)를 직접 조회해서 확인해요.

| ID | 시나리오 | 준비 | 실행 | 기대 결과 |
| --- | --- | --- | --- | --- |
| T-BPT-01 | 리프 분할 시 오른쪽 첫 키를 부모로 복사 | 키 1, 2, 3 삽입 | `insert(4, 40)` | 루트 `[3]`, 리프 `[1, 2]`, `[3, 4]`. 3은 리프에도 남아요 |
| T-BPT-02 | 내부 노드 분할 시 가운데 키를 부모로 이동 | 키 1~9 삽입 (루트 `[3, 5, 7]`) | `insert(10, 100)` | 루트 `[7]`, 내부 노드 `[3, 5]`, `[9]`, 높이 3. 7은 내부 노드에 남지 않고 리프 `[7, 8]`에만 있어요 |

T-BPT-02에서 10을 넣으면 리프 `[7, 8, 9, 10]`이 나뉘면서 9가 루트로 복사되고, 루트가 `[3, 5, 7, 9]`로 넘쳐요. 이때 가운데 키 7이 새 루트로 이동해요.

### `test_search`: `search(key)`

| ID | 시나리오 | 준비 | 실행 | 기대 결과 |
| --- | --- | --- | --- | --- |
| T-BPT-03 | 구분 키와 같은 키 | 키 1~4 삽입 (루트 `[3]`) | `search(3)` | `30` |
| T-BPT-04 | 모든 키 | 키 1~10 삽입 | `search(k)`, k = 1~10 | 모두 `k * 10` |
| T-BPT-05 | 가장 작은 키보다 작음 | 키 1~10 삽입 | `search(0)` | `None` |
| T-BPT-06 | 가장 큰 키보다 큼 | 키 1~10 삽입 | `search(11)` | `None` |
| T-BPT-07 | 빈 트리 | 없음 | `search(1)` | `None` |
| T-BPT-08 | 무작위 순서 삽입 | 키 1~1000을 고정 시드로 섞어서 삽입 | `search(k)`, k = 1~1000 | 모두 `k * 10` |

T-BPT-03은 [검색 규칙](../design/phase2.md#검색-규칙)의 `bisect_right`를 확인해요. 구분 키 3과 같은 키는 오른쪽 리프 `[3, 4]`로 가야 찾을 수 있어요. `bisect_left`를 쓰면 왼쪽 리프 `[1, 2]`로 내려가서 `None`이 나와요.

T-BPT-08은 분할이 여러 단계로 이어지는 경우를 확인해요.
