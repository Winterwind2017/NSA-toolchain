"""Electrical 数据层与 PLC 模块图的判据。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import Readback, verdict


def judge_ae_db(recorded: Dict[str, Any]) -> Dict[str, Any]:
    """只读打开元件库：库在、表在、行在，且**文件哈希没变**。"""
    rec = recorded or {}
    tables: List[str] = rec.get("tables") or []
    catalogs: List[str] = rec.get("catalogs") or []
    checks = {
        "aedata": bool(rec.get("aedata")),
        "catalogs": len(catalogs) >= 1,
        "opened": bool(rec.get("db")),
        "tables": len(tables) >= 1,
        "rows": int(rec.get("row_count") or 0) > 0,
        "sample": bool(rec.get("sample")),
        "readonly": bool(rec.get("unchanged")),
        "no_error": not rec.get("error"),
    }
    detail = {
        "aedata": rec.get("aedata"),
        "catalogs": catalogs,
        "db": rec.get("db"),
        "table_count": len(tables),
        "tables_sample": tables[:8],
        "sample_table": rec.get("sample_table"),
        "row_count": rec.get("row_count"),
        "sample": rec.get("sample"),
        "hash_before": rec.get("hash_before"),
        "hash_after": rec.get("hash_after"),
        "error": rec.get("error"),
    }
    return verdict(checks, detail, {"recorded": rec})


def judge_plc(rb: Readback, *, recorded: Dict[str, Any]) -> Dict[str, Any]:
    """PLC 模块图：规格来自数据库，图形计数 + 文字逐条对上。"""
    rec = recorded or {}
    drawn = rec.get("drawn") or {}
    counts = rb.memory.counts
    texts = [str(e.attrs.get("TextString") or "")
             for e in rb.memory.entities
             if "TEXT" in str(e.type).upper()]
    code = str(rec.get("CODE") or "")
    n_points = int(drawn.get("points") or 0)
    re_texts = [str(e.attrs.get("TextString") or "")
                for e in (rb.reopened.entities if rb.reopened else [])
                if "TEXT" in str(e.type).upper()]
    checks = {
        "spec": bool(rec.get("ok")),
        "lines": int(counts.get("LINE") or 0) == n_points,
        "circles": int(counts.get("CIRCLE") or 0) == n_points,
        "texts": len(texts) == int(drawn.get("texts") or -1),
        "polyline": int(counts.get("LWPOLYLINE") or 0) == 1,
        "code_text": bool(code) and any(code in t for t in texts),
        "points_label": n_points > 0 and any("I0.0" in t for t in texts),
        "reopen": (rb.reopened is None) or sorted(re_texts) == sorted(texts),
    }
    detail = {
        "spec": {k: rec.get(k) for k in ("CODE", "POINTS", "TYPE",
                                         "DESCRIPTION", "table", "db")},
        "drawn": drawn,
        "counts": counts,
        "texts": texts[:12],
        "error": rec.get("error"),
    }
    return verdict(checks, detail, {"recorded": rec, "counts": counts})
