"""结构化运行日志（JSONL）：每条事件一行，可机读、可汇总。

为什么不用 print：一次批量跑几十条能力，出问题要能回答"哪条、什么时候、什么错、
属于哪一类"。`core/diag.py` 负责分类，这里负责**落盘与汇总**。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RunLog:
    path: str
    case: str = ""
    events: List[Dict[str, Any]] = field(default_factory=list)
    _fh: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        d = os.path.dirname(self.path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        self._fh = open(self.path, "a", encoding="utf-8", newline="\n")

    # ── 写 ──
    def event(self, kind: str, level: str = "info", **fields: Any) -> Dict[str, Any]:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "case": self.case, "kind": kind, "level": level}
        rec.update({k: v for k, v in fields.items() if v is not None})
        self.events.append(rec)
        self._fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()
        return rec

    def info(self, kind: str, **fields: Any) -> Dict[str, Any]:
        return self.event(kind, "info", **fields)

    def warn(self, kind: str, **fields: Any) -> Dict[str, Any]:
        return self.event(kind, "warn", **fields)

    def error(self, exc: BaseException, kind: str = "failure",
              **fields: Any) -> Dict[str, Any]:
        from .diag import classify

        d = classify(exc)
        return self.event(kind, "error", error=d.raw, error_kind=d.kind,
                          retryable=d.retryable, hint=d.hint, **fields)

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:                                    # noqa: BLE001
            pass

    def __enter__(self) -> "RunLog":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def read_events(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                out.append({"level": "error", "kind": "corrupt_line",
                            "lineno": lineno, "raw": line[:120]})
    return out


def summarize(path: str) -> Dict[str, Any]:
    """按 level / kind 汇总，给"这轮跑得怎么样"一个数字答案。"""
    events = read_events(path)
    by_level: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}
    for e in events:
        by_level[str(e.get("level"))] = by_level.get(str(e.get("level")), 0) + 1
        k = e.get("error_kind") or e.get("kind")
        by_kind[str(k)] = by_kind.get(str(k), 0) + 1
    return {"total": len(events), "by_level": by_level, "by_kind": by_kind,
            "has_errors": by_level.get("error", 0) > 0}
