# 저장 계층

이 문서를 읽으면 저장 계층이 CSV 파일에 행을 쓰고 읽는 방법과, 각 함수가 언제 쓰이는지 알 수 있어요.
CSV를 고른 이유는 [ADR 0001](../../adr/0001-storage-format.md)에서 다뤄요.

## `Storage` 클래스

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

## CSV 변환

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
