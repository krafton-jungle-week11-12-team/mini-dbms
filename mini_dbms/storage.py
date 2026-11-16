"""CSV 파일을 열고 읽고 쓰는 코드는 모두 여기에 있어요."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterator


class Storage:
    def __init__(self, data_dir, schema):
        self.data_dir = Path(data_dir)
        self.schema = schema

    def _path(self, table: str) -> Path:
        return self.data_dir / f"{table}.csv"

    def append(self, table: str, record: list) -> int:
        """레코드를 파일 끝에 추가하고, 그 행의 시작 오프셋을 반환해요."""
        with open(self._path(table), "ab") as f:
            offset = f.tell()
            f.write(self._encode(record))
            return offset

    def scan(self, table: str) -> Iterator[tuple[int, list]]:
        """모든 행을 (오프셋, 레코드) 쌍으로 하나씩 넘겨요."""
        path = self._path(table)
        if not path.exists():
            return
        with open(path, "rb") as f:
            while True:
                offset = f.tell()
                line = f.readline()
                if not line:
                    break
                if line.strip():
                    yield offset, self._decode(table, line)

    def read_at(self, table: str, offset: int) -> list:
        """오프셋 위치의 행 하나만 읽어요."""
        with open(self._path(table), "rb") as f:
            f.seek(offset)
            return self._decode(table, f.readline())

    def _encode(self, record: list) -> bytes:
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerow(record)
        return buf.getvalue().encode("utf-8")

    def _decode(self, table: str, line: bytes) -> list:
        fields = next(csv.reader([line.decode("utf-8").rstrip("\r\n")]))
        return [
            int(v) if col_type == "INT" else v
            for (_, col_type), v in zip(self.schema[table], fields)
        ]
