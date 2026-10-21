"""P&ID 符号判据：线/圆/文字计数 + 三个位号都在 + 重开一致。"""

from __future__ import annotations

from typing import Any, Dict, List

from .base import Readback, verdict


def judge_pid(rb: Readback, *, recorded: Dict[str, Any]) -> Dict[str, Any]:
    rec = recorded or {}
    counts = rb.memory.counts
    texts = sorted(str(e.attrs.get("TextString") or "")
                   for e in rb.memory.entities if "TEXT" in str(e.type).upper())
    re_texts = sorted(str(e.attrs.get("TextString") or "")
                      for e in (rb.reopened.entities if rb.reopened else [])
                      if "TEXT" in str(e.type).upper())
    checks = {
        "lines": int(counts.get("LINE") or 0) == int(rec.get("lines") or -1),
        "circles": int(counts.get("CIRCLE") or 0) == int(rec.get("circles") or -1),
        "texts": texts == sorted(rec.get("texts") or []),
        "tags": all(t in texts for t in ("HV-01", "P-01", "PI-01")),
        "reopen": (rb.reopened is None) or re_texts == texts,
    }
    detail = {"counts": counts, "texts": texts,
              "expected": {"lines": rec.get("lines"),
                           "circles": rec.get("circles"),
                           "texts": rec.get("texts")}}
    return verdict(checks, detail, {"counts": counts, "texts": texts})
