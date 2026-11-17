from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

ACTIONS_COLUMNS = ["user_id", "song_id", "gmt_create", "action_type", "Ds"]
SONGS_COLUMNS = [
    "song_id",
    "artist_id",
    "publish_time",
    "song_init_plays",
    "Language",
    "Gender",
]
GENERIC_HEADER_PREFIX = "col_"

_HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")


@dataclass(frozen=True)
class DatasetSpec:
    kind: str
    columns: list[str]
    has_header: bool

    def to_dict(self) -> dict:
        return {"kind": self.kind, "columns": self.columns, "has_header": self.has_header}


def _first_line(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line in handle:
            if line.strip():
                return line.rstrip("\r\n")
    return ""


def _looks_numeric(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def detect_dataset(path: Path) -> DatasetSpec:
    """根据首行结构确定性识别天池数据表，其余文件按通用 CSV 处理。

    不在此处读取整份文件：1.33 GB 行为表也必须保持常量级开销。
    """
    line = _first_line(path)
    if not line:
        raise ValueError("文件为空，无法识别数据结构")

    fields = [field.strip() for field in next(csv.reader([line]))]
    count = len(fields)

    if (
        count == 5
        and _HEX32.match(fields[0])
        and _HEX32.match(fields[1])
        and fields[2].isdigit()
        and fields[3] in {"1", "2", "3"}
        and len(fields[4]) == 8
        and fields[4].isdigit()
    ):
        return DatasetSpec("actions", ACTIONS_COLUMNS, False)

    if (
        count == 6
        and _HEX32.match(fields[0])
        and _HEX32.match(fields[1])
        and len(fields[2]) == 8
        and fields[2].isdigit()
        and fields[3].isdigit()
    ):
        return DatasetSpec("songs", SONGS_COLUMNS, False)

    has_header = not all(_looks_numeric(field) for field in fields)
    if has_header:
        columns = [field or f"{GENERIC_HEADER_PREFIX}{index + 1}" for index, field in enumerate(fields)]
    else:
        columns = [f"{GENERIC_HEADER_PREFIX}{index + 1}" for index in range(count)]
    return DatasetSpec("generic", columns, has_header)
