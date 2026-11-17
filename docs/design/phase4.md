# Phase 4 설계

이 문서를 읽으면 API 서버가 스레드 풀로 여러 요청을 동시에 받고, 테이블 락으로 엔진의 공유 상태를 지키려면 무엇을 어떻게 바꾸는지 알 수 있어요.
요구사항은 [Phase 4 요구사항](../requirements/phase4.md)에, 스레드 풀 구조와 락 단위를 고른 이유는 [ADR 0003](../adr/0003-server-architecture.md)과 [ADR 0004](../adr/0004-locking.md)에 있어요.
요청 검사, 예외 변환, 응답 구조는 [Phase 3 설계](phase3.md)와 같아요.

## 처리 흐름

```
클라이언트 ──→ OS 대기열 ──→ 메인 스레드 ──put_nowait()──→ 작업 큐 ──get()──→ 워커 스레드 N개
                              │ (accept)                                     │
                              │ 큐가 가득 참                                   ├─ 요청 검사, tokenize, parse, validate (락 없이 동시에)
                              ↓                                              ├─ Executor.run (테이블 락 안에서 하나씩)
                         503 응답 후 닫기                                       └─ 응답 쓰기 → 소켓 닫기
```

- 메인 스레드는 연결을 받아 작업 큐에 넣기만 하고 요청 내용을 읽지 않아요.
- 요청을 읽고 처리하고 응답하는 일은 워커 스레드가 해요. 워커 안에서 실행되는 `QueryHandler`는 Phase 3와 같아요.
- `next_id`, B+ 트리, CSV를 다루는 `Executor.run`만 테이블 락 안에서 실행돼요.

## 목차

1. [스레드 역할](#스레드-역할)
2. [스레드 풀](#스레드-풀)
3. [작업 큐가 가득 찼을 때](#작업-큐가-가득-찼을-때)
4. [소켓 읽기 timeout](#소켓-읽기-timeout)
5. [테이블 락](#테이블-락)
6. [바꾸는 파일](#바꾸는-파일)

## 스레드 역할

이 항목을 읽으면 메인 스레드와 워커 스레드가 각각 무엇을 하는지 알 수 있어요.

| 스레드 | 개수 | 하는 일 | 하지 않는 일 |
| --- | --- | --- | --- |
| 메인 스레드 | 1 | `serve_forever()` 루프에서 연결을 `accept()`하고 (소켓, 주소)를 작업 큐에 넣어요. 큐가 가득 차면 503으로 거절해요 | 요청을 읽거나 엔진을 호출하지 않아요 |
| 워커 스레드 | N = 4 | 작업 큐에서 (소켓, 주소)를 꺼내 `QueryHandler`로 처리하고 소켓을 닫아요 | 다른 워커와 직접 주고받는 것이 없어요. 작업 큐로만 연결돼요 |

메인 스레드와 워커 스레드는 서로를 기다리지 않아요.
메인 스레드는 큐에 넣거나 거절한 뒤 바로 다음 연결을 받고, 워커는 큐가 비어 있으면 `get()`에서 기다려요.

## 스레드 풀

이 항목을 읽으면 `QueryServer`가 작업 큐와 워커를 어떻게 만들고, 요청을 어떻게 넘기는지 알 수 있어요.

### 작업 큐와 워커 만들기 (`TP-01`)

`QueryServer`가 시작할 때 크기 M인 작업 큐와 워커 N개를 만들어요.
워커는 상태를 들고 있지 않아서 `threading.Thread` 리스트로 보관해요.

```python
class QueryServer(HTTPServer):
    def __init__(self, server_address, engine, workers=4, queue_size=16):
        super().__init__(server_address, QueryHandler)
        self.engine = engine
        self.jobs = queue.Queue(maxsize=queue_size)   # 작업 큐
        self.workers = [                              # 워커 목록
            threading.Thread(target=self._worker, name=f"worker-{i}")
            for i in range(1, workers + 1)
        ]
        for t in self.workers:
            t.start()
```

| 인자 | 의미 | 기본값 |
| --- | --- | --- |
| `workers` | 워커 스레드 수 N. 동시에 처리할 수 있는 요청 수예요 | `4` |
| `queue_size` | 작업 큐 크기 M. 워커가 모두 바쁠 때 기다릴 수 있는 요청 수예요 | `16` |

인자로 받는 이유는 테스트에서 `workers=1, queue_size=1`처럼 작게 줘서, 큐가 가득 찬 상황을 빠르게 만들기 위해서예요.
스레드 이름은 로그에서 어느 워커가 처리했는지 구분하는 데 써요.

### 메인 스레드: 큐에 넣기 (`TP-02`)

`HTTPServer`는 `accept()`로 얻은 연결을 `process_request()`에 넘겨요.
지금은 이 메서드가 핸들러 실행까지 직접 하는데, 큐에 넣기만 하도록 바꿔요.

```python
# 지금 (부모 클래스 TCPServer의 기본 동작)
def process_request(self, request, client_address):
    self.finish_request(request, client_address)   # QueryHandler 실행까지 여기서 다 함
    self.shutdown_request(request)                 # 소켓 닫기

# 바꾼 뒤
def process_request(self, request, client_address):
    try:
        self.jobs.put_nowait((request, client_address))   # 큐에 넣고 바로 반환
    except queue.Full:
        self._reject(request)                             # 작업 큐가 가득 찼을 때
```

`request`는 요청 내용이 아니라 `accept()`로 얻은 연결 소켓이에요.
HTTP 요청 바이트는 아직 그 소켓의 수신 버퍼에 있고, 워커가 꺼낸 뒤에 읽어요.

### 워커 스레드: 꺼내서 처리하기 (`TP-04` ~ `TP-07`)

```python
def _worker(self):
    while True:
        job = self.jobs.get()                              # 큐가 비어 있으면 여기서 기다림 (TP-05)
        if job is None:                                    # 종료 신호
            return
        request, client_address = job
        try:
            self.finish_request(request, client_address)   # QueryHandler 생성 → 요청 처리 → 응답 (TP-04)
        except Exception:
            self.handle_error(request, client_address)     # 로그만 남기고 다음 작업으로 (TP-06)
        finally:
            self.shutdown_request(request)                 # 소켓은 반드시 닫음 (TP-07)
```

- `finish_request()`와 `shutdown_request()`는 `HTTPServer`가 원래 쓰던 메서드라, 핸들러 쪽은 바꾸지 않아요.
- 엔진 예외는 `QueryHandler._execute()`가 이미 500으로 바꿔서 여기까지 오지 않아요. 여기서 잡는 건 클라이언트가 연결을 먼저 끊어 응답을 쓰다 실패하는 경우(`BrokenPipeError`) 같은 것이에요.
- `handle_error()`의 기본 동작은 stderr에 스택 트레이스를 찍는 거라, `logger.exception()`으로 바꿔서 서버 로그에 남겨요.

### 종료

`server_close()`에서 워커 수만큼 종료 신호(`None`)를 큐에 넣고, 모든 워커를 `join()`으로 기다려요.

```python
def server_close(self):
    for _ in self.workers:
        self.jobs.put(None)
    for t in self.workers:
        t.join()
    super().server_close()
```

워커는 `get()`에서 잠들어 있어서, 밖에서 끝내라고 알릴 방법이 큐밖에 없어요.
`daemon=True`로 띄우면 이 코드가 필요 없지만, 처리 중인 요청이 응답 없이 끊길 수 있어요. 테스트에서 서버를 띄웠다 내렸다 하므로 `join()`으로 기다려요.

## 작업 큐가 가득 찼을 때

이 항목을 읽으면 메인 스레드가 큐에 넣지 못한 요청을 어떻게 거절하는지 알 수 있어요. (`TP-03`)

메인 스레드는 기다리지 않고 바로 거절해요.

```
1. accept()로 연결을 꺼냄
2. put_nowait() 시도 → 큐가 가득 차서 실패
3. 그 연결에 503을 보내고 소켓을 닫음   ← 이 요청은 여기서 끝, 어디에도 저장 안 함
4. 바로 select()로 돌아가 다음 연결을 받음
```

거절한 요청은 나중에 처리하지 않아요. 클라이언트가 다시 보내야 해요.
다음 연결이 오면 그 순간의 큐 상태로 다시 판단해요. 그 사이에 워커가 큐에서 하나를 꺼내 갔으면 넣을 수 있어요.

### 응답

```http
HTTP/1.0 503 Service Unavailable
Content-Type: application/json; charset=utf-8
Content-Length: 84
Retry-After: 1

{"ok": false, "error": {"code": "SERVICE_UNAVAILABLE", "message": "server is busy"}}
```

| 항목 | 의미 | 값 |
| --- | --- | --- |
| `error.code` | 실패 원인. Phase 3 [응답 구조](phase3.md#응답-구조)의 실패 형식을 따라요 | `"SERVICE_UNAVAILABLE"` |
| `Retry-After` | 클라이언트가 다시 보내기 전에 기다릴 초 | `1` |

### 메인 스레드에서 거절하는 방법

`QueryHandler`를 거치지 않고 메인 스레드가 소켓에 직접 써요.
메인 스레드가 오래 붙잡히면 다음 연결을 받지 못하므로, 기다리는 일을 하지 않아요.

```python
def _reject(self, request):
    try:
        request.setblocking(False)
        try:
            while request.recv(65536):   # 이미 도착한 데이터만 비움
                pass
        except BlockingIOError:
            pass
        request.sendall(BUSY_RESPONSE)
    except OSError:
        pass
    finally:
        self.shutdown_request(request)
```

- **요청을 끝까지 읽지 않아요.** 바디를 다 기다리면 느린 클라이언트 하나가 메인 스레드를 붙잡아요. 논블로킹으로 이미 도착한 데이터만 비워요.
- **도착한 데이터는 비우고 닫아요.** 읽지 않은 데이터를 남긴 채 닫으면 OS가 RST를 보내서, 클라이언트가 503을 읽기 전에 연결이 끊길 수 있어요. Phase 3의 `_discard_body()`와 같은 이유예요.
- **응답은 미리 만들어 둔 바이트예요.** `BUSY_RESPONSE`는 모듈 상수로 한 번만 만들어요. 100바이트 남짓이라 송신 버퍼에 바로 들어가서 막히지 않아요.
- **실패해도 무시해요.** 클라이언트가 이미 연결을 끊었으면 `sendall()`이 `OSError`를 내는데, 거절할 요청이라 할 일이 없어요.

## 소켓 읽기 timeout

이 항목을 읽으면 느린 클라이언트가 워커를 오래 붙잡지 않게 무엇을 바꾸는지 알 수 있어요. (`TP-08`)

`QueryHandler.timeout`을 10에서 5로 바꿔요.

```python
class QueryHandler(BaseHTTPRequestHandler):
    timeout = 5
```

- `StreamRequestHandler`가 이 값으로 `socket.settimeout()`을 불러요. 전체 처리 시간이 아니라 **한 번 읽거나 쓸 때마다** 기다리는 최대 시간이에요.
- 5초 동안 데이터가 오지 않으면 `TimeoutError`가 나고, `BaseHTTPRequestHandler.handle_one_request()`가 이를 잡아 로그를 남기고 응답 없이 연결을 닫아요. 우리가 따로 잡지 않아도 돼요.
- 워커가 N = 4개뿐이라, 바디를 보내지 않는 클라이언트 4개면 워커가 모두 막혀요. timeout을 줄이면 그 시간이 10초에서 5초로 줄어요.

## 테이블 락

이 항목을 읽으면 실행기가 테이블 락을 어디에 두고 언제 잡는지 알 수 있어요. (`LK-01` ~ `LK-04`)

### 락 만들기 (`LK-01`)

`Executor.__init__`에서 테이블마다 락을 하나씩 만들어요.

```python
# Executor.__init__
self.locks = {table: threading.Lock() for table in schema}
```

`_load()`는 워커가 생기기 전에 `Engine`을 만들면서 끝나므로 락을 잡지 않아요.

### 락 잡기 (`LK-02` ~ `LK-04`)

INSERT와 SELECT를 부르는 `run()` 한 곳에서 락을 잡아요.

```python
def run(self, ast) -> Result:
    with self.locks[ast.table]:
        if isinstance(ast, InsertStmt):
            return self.run_insert(ast)
        if isinstance(ast, SelectStmt):
            return self.run_select(ast)
    raise TypeError(f"실행할 수 없는 AST: {ast!r}")
```

- **INSERT와 SELECT가 같은 락을 잡아요.** SELECT도 잡아야 INSERT가 노드를 분할하거나 CSV에 쓰는 도중의 상태를 읽지 않아요.
- **`run_insert()` 전체가 락 안이에요.** id 발급 → `append()` → 트리 삽입 → `next_id` 증가가 다른 워커에 끼어들림 없이 한 번에 끝나요.
- **`with` 문이라 예외가 나도 락을 놓아요.** 락을 놓지 않으면 그 테이블의 모든 요청이 멈춰요.
- **`run_insert()`와 `run_select()` 안에서 또 잡지 않아요.** `threading.Lock`은 같은 스레드가 두 번 잡을 수 없어서, `run()`과 그 안에서 같은 락을 잡으면 그 워커가 영원히 멈춰요.

`tokenize()`, `parse()`, `validate()`는 공유 상태를 바꾸지 않아서 락 밖에서 동시에 실행돼요.

### 동시 실행 예

워커 1과 워커 2가 users 테이블에 INSERT를 거의 동시에 보낸 경우예요.

| 시점 | 워커 1 | 워커 2 | users 락 |
| --- | --- | --- | --- |
| 1 | tokenize, parse, validate | tokenize, parse, validate | 비어 있음 |
| 2 | 락 잡음. id 5 발급, `append()`, 트리 삽입, `next_id = 6` | 락 기다림 | 워커 1 |
| 3 | 락 놓고 201 응답 | 락 잡음. id 6 발급 | 워커 2 |
| 4 | | 락 놓고 201 응답 | 비어 있음 |

지금 스키마에는 users 테이블 하나뿐이라, 테이블 락이 사실상 전역 락처럼 동작해요.
같은 테이블의 SELECT끼리도 기다리는 것은 ADR 0004에서 받아들인 단점이에요.

## 바꾸는 파일

| 파일 | 바꾸는 것 | 요구사항 |
| --- | --- | --- |
| `server.py` | `QueryServer`에 작업 큐, 워커 목록, `process_request()`, `_worker()`, `_reject()`, `server_close()`, `handle_error()` 추가. `BUSY_RESPONSE` 상수 추가. `QueryHandler.timeout`을 5로. `main()`에 `--workers`, `--queue-size` 옵션 추가 | `TP-01` ~ `TP-08` |
| `executor.py` | `Executor.__init__`에 `locks` 추가. `run()`에서 테이블 락 잡기 | `LK-01` ~ `LK-04` |

`QueryHandler`의 요청 검사와 예외 변환, 엔진의 나머지 코드는 바꾸지 않아요.
