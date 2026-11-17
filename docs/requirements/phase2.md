# Phase 2 요구사항

이 문서를 읽으면 Phase 2 B+ 트리 인덱스를 붙이기 위해 엔진, 실행기, 저장 계층이 무엇을 해야 하는지 ID로 확인할 수 있어요.
Phase 1 요구사항은 [phase1.md](phase1.md)에 있고, 이 문서의 ID는 Phase 1 번호에 이어서 붙여요.

처리 흐름: `CLI → 토크나이저 → 파서 → AST 검증 → 실행기 → (B+ 트리 인덱스) → 저장 계층(CSV)`

- INSERT: 실행기가 id를 자동 부여하고, `append()`가 반환한 offset과 함께 `(id, offset)`을 인덱스 트리에 넣어요.
- SELECT: `WHERE id = 값`이면 인덱스 트리에서 offset을 찾아 그 행 하나만 읽고, 그 외 조건은 Phase 1처럼 선형 탐색해요.

## 엔진

| ID | 요구사항 | 비고 |
| --- | --- | --- |
| ENG-01 | 엔진은 테이블과 함께 인덱스로 사용할 컬럼 정보를 가져야 한다. | `engine.py`의 `SCHEMA` 옆에 둠. 예: `INDEX_KEYS = {"users": "id"}` |

## 실행기

| ID | 요구사항 | 비고 |
| --- | --- | --- |
| EXE-04 | 실행기는 레코드 삽입 시 id를 자동 부여해야 한다. | `next_id`는 AST가 아니라 실행기가 테이블별로 관리. 사용자가 id 없이 값만 넣으므로 AST 검증(`AST-01`)의 값 개수 기준도 바꿔야 함 |
| EXE-05 | 실행기는 프로그램을 종료 후 재시작할 때 인덱스 트리와 `next_id`를 복구할 수 있어야 한다. | 기동 시 `scan()`으로 `(id, offset)`을 트리에 다시 넣고, `next_id = 최대 id + 1`. `STO-02` 사용 |
| EXE-06 | 실행기는 INSERT 시 자동 부여된 id를 key로, `append()`가 반환한 offset을 value로 인덱스 트리에 삽입해야 한다. | 순서: id 부여 → `append()` → 트리 삽입 → `next_id` 증가. Phase 1 `EXE-02`를 구체화 |
| EXE-07 | 실행기는 SELECT의 WHERE가 `id = 값`이면 인덱스 트리에서 해당 id의 offset을 찾고, 저장 계층을 통해 CSV 파일에서 해당 레코드 한 줄만 읽어야 한다. | id가 트리에 없으면 빈 결과(0건). 그 외 조건은 Phase 1 `EXE-03`처럼 선형 탐색. `STO-03` 사용 |

## 저장 계층

아래 세 항목은 Phase 1에서 이미 구현했어요. Phase 2에서 어떻게 쓰이는지 함께 보려고 다시 적어요.

| ID | 요구사항 | 비고 |
| --- | --- | --- |
| STO-01 | 저장 계층은 append 시 CSV 파일에서 레코드가 추가된 위치(offset)를 반환해야 한다. | offset은 바이트 단위(쓰기 전 `tell()` 값). `EXE-06`에서 사용 |
| STO-02 | 저장 계층은 scan 시 각 레코드와 그 offset을 함께 반환해 인덱스를 재구축할 수 있게 해야 한다. | `scan()`이 `(offset, 레코드)`를 한 행씩 넘김. `EXE-05`에서 사용 |
| STO-03 | 저장 계층은 table에 해당하는 CSV 파일에서 offset 위치의 레코드를 읽을 수 있어야 한다. | `read_at(table, offset)`: `seek` 후 한 줄만 읽음. `EXE-07`에서 사용 |
