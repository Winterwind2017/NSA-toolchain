"""两张图的差异比对（对照 CADCraft `crates/engine/cmd/file/compare.rs`）。

用途很具体：**改图后重跑，图有没有变形**。我们原来的判据只能验"实体数对不对"，
这里给出逐实体的增/删/改（含图层、几何量），并能输出人能读的报告。

设计取舍：
* 以**句柄**为身份；没有句柄的按"类型#序号"占位（明确标注不是真身份）；
* 几何比较按字段容差，不按文件字节（不同 DXF 写出器的格式差异不算改图）；
* 结论分三类，不做模糊匹配——宁可多报 also 不假"一致"。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .document import Document, Entity

TOL = 1e-6


def _index(doc: Document) -> Dict[str, Entity]:
    out: Dict[str, Entity] = {}
    counters: Dict[str, int] = {}
    for ent in doc.entities():
        if ent.handle:
            key = ent.handle
        else:
            n = counters.get(ent.type, 0)
            counters[ent.type] = n + 1
            key = "%s#%d" % (ent.type, n)
        out[key] = ent
    return out


def _geom(ent: Entity) -> Dict[str, object]:
    """抽几何量（只取常见组码，容差比较）。"""
    out: Dict[str, object] = {"layer": ent.layer or ""}
    for code in (10, 20, 30, 11, 21, 31, 40, 50, 51, 1, 2):
        vals = ent.get_all(code)
        if vals:
            try:
                out["c%d" % code] = [float(v) for v in vals]
            except ValueError:
                out["c%d" % code] = list(vals)
    return out


def _same(a: object, b: object) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= TOL
    return a == b


@dataclass
class Change:
    key: str
    type: str
    fields: List[str] = field(default_factory=list)


@dataclass
class CompareReport:
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    changed: List[Change] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)

    @property
    def identical(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def to_dict(self) -> dict:
        return {"added": self.added, "removed": self.removed,
                "changed": [{"key": c.key, "type": c.type, "fields": c.fields}
                            for c in self.changed],
                "counts": self.counts, "identical": self.identical}

    def to_text(self) -> str:
        if self.identical:
            return "两张图一致（%s）" % self.counts
        lines = ["差异：新增 %d / 删除 %d / 改动 %d（%s）"
                 % (len(self.added), len(self.removed), len(self.changed), self.counts)]
        lines += ["  + %s" % k for k in self.added]
        lines += ["  - %s" % k for k in self.removed]
        for c in self.changed:
            lines.append("  ~ %s(%s)：%s" % (c.key, c.type, ", ".join(c.fields)))
        return "\n".join(lines)


def compare(old: Document, new: Document) -> CompareReport:
    a, b = _index(old), _index(new)
    rep = CompareReport(counts={"old": len(a), "new": len(b)})
    for key in sorted(set(a) - set(b)):
        rep.removed.append(key)
    for key in sorted(set(b) - set(a)):
        rep.added.append(key)
    for key in sorted(set(a) & set(b)):
        ea, eb = a[key], b[key]
        if ea.type != eb.type:
            rep.changed.append(Change(key, eb.type, ["type"]))
            continue
        ga, gb = _geom(ea), _geom(eb)
        diff = sorted(k for k in set(ga) | set(gb) if not _same(ga.get(k), gb.get(k)))
        if diff:
            rep.changed.append(Change(key, eb.type, diff))
    return rep
