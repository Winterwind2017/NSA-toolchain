"""job / result 的 JSON 协议（唯一跨进程契约）。"""

from __future__ import annotations

import json
import os
import time

SCHEMA = 1
DONE_MARK = "NXKIT_DONE"


def new_job(workdir: str, caps: list[dict], src: str) -> dict:
    return {
        "schema": SCHEMA,
        "workdir": workdir,
        "src": src,
        "caps": caps,
        "result": os.path.join(workdir, "result.json"),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def write_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def empty_result() -> dict:
    return {"schema": SCHEMA, "caps": []}


def append_cap(result: dict, path: str, record: dict) -> None:
    result["caps"].append(record)
    write_json(path, result)
