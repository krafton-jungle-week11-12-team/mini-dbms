# CLI

이 문서를 읽으면 CLI가 SQL 파일을 문장으로 나누고, 문장을 하나씩 실행하는 방법을 알 수 있어요.
인자와 파일 검사는 [에러 처리](errors.md#cli)에서 다뤄요.

## 문장 분리

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

## 문장 실행

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

실행기는 출력하지 않고 [Result](executor.md#결과-형식)를 반환해요. 화면에 표로 출력하는 건 CLI의 일이에요.
