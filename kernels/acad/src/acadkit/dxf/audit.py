"""图纸自检（检查项参照 CADCraft `crates/engine/audit.rs`）。

AutoCAD 的 `AUDIT` 我们调不动（会弹报告框、且判据不可读），但"交付前自检"
本身可以离线做：拿 DXF 结构就能查出大部分低级错误。这里只做**能从文件结构判定**的项，
不做几何合法性（那要真机）。

每条问题都带 `rule / severity / handle / detail`，方便机器消费与人工看。
严重度：error（图可能打不开/几何坏）> warn（规范问题）> info（提示）。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from .document import Document, Entity

# 需要坐标的实体类型（用来查非有限值）
_COORD_TYPES = ("LINE", "CIRCLE", "ARC", "LWPOLYLINE", "POLYLINE", "TEXT", "MTEXT",
                "INSERT", "ELLIPSE", "SPLINE", "POINT")


def _num(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _finite_pairs(ent: Entity) -> List[str]:
    """返回值为非有限数值的组码列表。"""
    bad = []
    for code, value in ent.pairs:
        if 10 <= code <= 59 or 140 <= code <= 149:
            f = _num(value)
            if f is not None and (f != f or f in (float("inf"), float("-inf"))):
                bad.append("%d=%s" % (code, value))
    return bad


def audit(doc: Document) -> Dict[str, object]:
    """返回 {issues, counts}。issues 为空表示通过。"""
    issues: List[dict] = []
    ents = doc.entities()
    layers = doc.layers()
    layer_names = {v["name"] for v in layers.values() if v.get("name")}

    def add(rule: str, severity: str, ent: Optional[Entity], detail: str) -> None:
        issues.append({"rule": rule, "severity": severity,
                       "handle": (ent.handle if ent else None),
                       "type": (ent.type if ent else None),
                       "detail": detail})

    # 1) 重复句柄
    seen: Dict[str, Entity] = {}
    for ent in ents:
        h = ent.handle
        if not h:
            add("missing_handle", "ignore" if False else "info", ent, "实体没有句柄")
            continue
        if h in seen:
            add("duplicate_handle", "error", ent, "句柄 %s 与 %s 重复"
                % (h, seen[h].type))
        else:
            seen[h] = ent

    for ent in ents:
        # 2) 非有限坐标
        bad = _finite_pairs(ent)
        if bad:
            add("non_finite_coord", "error", ent, "非有限数值：%s" % ", ".join(bad))
            continue                                   # 后面的数值检查没意义

        # 3) 零长度线
        if ent.type == "LINE":
            p = ent.point()
            xs, ys = ent.floats(11), ent.floats(21)
            if p and xs and ys:
                if math.hypot(xs[0] - p[0], ys[0] - p[1]) < 1e-9:
                    add("zero_length_line", "warn", ent, "起终点重合")

        # 4) 非正半径
        if ent.type in ("CIRCLE", "ARC"):
            r = _num(ent.get(40))
            if r is None:
                add("missing_radius", "error", ent, "缺少半径组码 40")
            elif r <= 0:
                add("bad_radius", "error", ent, "半径 %r ≤ 0" % r)

        # 5) 缺少所引用的图层（仅当文件确实有图层表时才有意义）
        if layer_names and ent.layer and ent.layer not in layer_names:
            add("unknown_layer", "warn", ent, "图层 %r 不在 TABLES 里" % ent.layer)

        # 6) LWPOLYLINE 连续重复顶点
        if ent.type == "LWPOLYLINE":
            xs = [_num(v) for v in ent.get_all(10)]
            ys = [_num(v) for v in ent.get_all(20)]
            if len(xs) != len(ys):
                add("polyline_xy_mismatch", "error", ent,
                    "顶点数不一致（X=%d, Y=%d）" % (len(xs), len(ys)))
            else:
                for i in range(1, len(xs)):
                    if xs[i] is not None and ys[i] is not None \
                            and xs[i - 1] is not None and ys[i - 1] is not None:
                        if abs(xs[i] - xs[i - 1]) < 1e-12 and abs(ys[i] - ys[i - 1]) < 1e-12:
                            add("duplicate_vertex", "warn", ent,
                                "第 %d/%d 个顶点重复" % (i, i + 1))

        # 7) 文字高度非正
        if ent.type in ("TEXT", "MTEXT"):
            h = _num(ent.get(40))
            if h is not None and h <= 0:
                add("bad_text_height", "error", ent, "字高 %r ≤ 0" % h)

    counts: Dict[str, int] = {}
    for item in issues:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
    return {"entities": len(ents), "issues": issues, "counts": counts,
            "ok": not any(i["severity"] == "error" for i in issues)}


def report_text(result: Dict[str, object]) -> str:
    """给人看的一行摘要 + 明细。"""
    issues = result["issues"]  # type: ignore[index]
    head = "实体 %d，问题 %d 条（%s）" % (
        result["entities"], len(issues),                          # type: ignore[arg-type]
        ", ".join("%s=%d" % kv for kv in sorted(result["counts"].items())) or "无")  # type: ignore[union-attr]
    lines = [head]
    for item in issues:                                          # type: ignore[union-attr]
        lines.append("  [%s] %s %s(%s): %s"
                     % (item["severity"], item["rule"], item["type"],
                        item["handle"], item["detail"]))
    return "\n".join(lines)
