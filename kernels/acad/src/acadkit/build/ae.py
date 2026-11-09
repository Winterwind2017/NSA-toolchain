"""Electrical 数据 + PLC 模块图的 builder（都不需要 AutoCAD，只读 AeData）。"""

from __future__ import annotations

import os
from typing import Any, Dict

from .. import ae
from ..core import com
from .helpers import add, dbl, ms_of, pt


def build_ae_db(doc: Any, ctx: Dict[str, Any]) -> None:
    """只读打开 Electrical 的元件库：数表、数行、读一条样例，并证明文件没改。"""
    rec: Dict[str, Any] = {"ok": False, "error": None}
    try:
        root = ae.aedata_dir()
        rec["aedata"] = root
        if not root:
            rec["error"] = ("没有 AeData（默认 ~/Documents/Acade 2025/AeData，"
                            "可用 DSH_AE_AEDATA 指定）")
            ctx["artifacts"]["ae_db"] = rec
            ctx["notes"].append(rec["error"])
            return
        catalogs = ae.catalog_dbs(root)
        rec["catalogs"] = [os.path.basename(p) for p in catalogs]
        if not catalogs:
            rec["error"] = "Catalogs 下没有 .mdb"
            ctx["artifacts"]["ae_db"] = rec
            return
        db = catalogs[0]
        rec["db"] = os.path.basename(db)
        before = ae.sha256(db)
        conn = ae.connect(db)
        try:
            names = ae.tables(conn)
            rec["tables"] = names
            table = "MATRIX" if "MATRIX" in names else (names[0] if names else None)
            rec["sample_table"] = table
            if table:
                rec["row_count"] = ae.count(conn, table)
                rows = ae.records(conn, "SELECT TOP 3 * FROM [%s]" % table)
                rec["sample"] = {
                    k: (str(v)[:40] if v is not None else None)
                    for k, v in (rows[0].items() if rows else [])
                    if v is not None
                }
                rec["sample_rows"] = len(rows)
        finally:
            ae.close(conn)
        rec["hash_before"] = before
        rec["hash_after"] = ae.sha256(db)
        rec["unchanged"] = rec["hash_before"] == rec["hash_after"]
        rec["ok"] = True
    except Exception as exc:                        # noqa: BLE001
        rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        ctx["notes"].append("ae.db 失败：" + rec["error"])
    ctx["artifacts"]["ae_db"] = rec


def build_plc_module(doc: Any, ctx: Dict[str, Any]) -> None:
    """按 `ace_plc.mdb` 的模块规格画 PLC I/O 模块图（不依赖 ACADE 模板）。

    规格来自数据库（CODE / POINTS / TYPE / DESCRIPTION），图形是程序化绘制：
    模块框 + 每点一条线/端子/位号。这样在 `<<VANILLA>>` 下也能出 PLC 图。
    """
    params = ctx.get("params") or {}
    rec: Dict[str, Any] = {"ok": False}
    try:
        spec = ae.module_spec(table=params.get("table"))
        rec.update({k: spec.get(k) for k in ("CODE", "POINTS", "TYPE",
                                             "DESCRIPTION", "RATING")})
        rec["table"] = spec.get("_table")
        rec["db"] = os.path.basename(spec.get("_db") or "")
        rec["ok"] = True
    except Exception as exc:                        # noqa: BLE001
        rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        ctx["artifacts"]["plc"] = rec
        ctx["notes"].append("PLC 规格读取失败：" + rec["error"])
        return

    points = params.get("points") or rec.get("POINTS")
    try:
        n_points = int(points)
    except (TypeError, ValueError):
        n_points = 8
    code = str(rec.get("CODE") or "PLC-MODULE")
    desc = str(rec.get("DESCRIPTION") or "")

    ms = ms_of(doc)
    pl = com.retry(lambda: ms.AddLightWeightPolyline(
        dbl([0, 0, 120, 0, 120, 80, 0, 80])), label="AddLightWeightPolyline")
    pl.Closed = True
    add(ms, "AddText", code, pt(4, 72, 0), 4.0, label="AddText")
    if desc:
        add(ms, "AddText", desc[:40], pt(4, 64, 0), 3.0, label="AddText")
    for i in range(n_points):
        y = 56 - i * 6
        add(ms, "AddLine", pt(8, y, 0), pt(40, y, 0), label="AddLine")
        add(ms, "AddCircle", pt(44, y, 0), 1.2, label="AddCircle")
        add(ms, "AddText", "I0.%d" % i, pt(48, y - 1.5, 0), 2.5, label="AddText")
    rec["drawn"] = {"points": n_points, "lines": n_points,
                    "circles": n_points, "texts": n_points + (2 if desc else 1),
                    "polyline": 1}
    ctx["artifacts"]["plc"] = rec
