"""清理：重复实体（overkill）与未用对象（purge）。

参照 CADCraft `crates/engine` 的 `overkill` / `cmd/blocks/purge.rs`。
都只做**判定与报告**，不直接改图——改图由调用方决定（并应留可回滚的副本）。

* `find_duplicates`  同类型、几何在容差内相同 → 视为重复（保留句柄最小的）
* `find_unused`      TABLES 里没人引用的图层/线型/块（AutoCAD 的 PURGE 安全版）
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from .document import Document, Entity

# 几何指纹只用到这些组码（够区分常见实体，且不误判）
_GEO_CODES = {
    "LINE": (10, 20, 30, 11, 21, 31),
    "CIRCLE": (10, 20, 30, 40),
    "ARC": (10, 20, 30, 40, 50, 51),
    "TEXT": (10, 20, 1, 40),
    "MTEXT": (10, 20, 1, 40),
    "POINT": (10, 20, 30),
    "INSERT": (10, 20, 30, 2, 41, 42, 50),
}


def _round(v: Optional[str], nd: int) -> Optional[float]:
    if v is None:
        return None
    try:
        return round(float(v), nd)
    except ValueError:
        return None


def geo_key(ent: Entity, ndigits: int = 6) -> Optional[Tuple]:
    """几何指纹；不认识的类型返回 None（不参与去重，避免误删）。"""
    codes = _GEO_CODES.get(ent.type)
    if not codes:
        return None
    if ent.type == "LINE":
        # 直线反向画仍是同一条线：端点排序后再做指纹
        a = tuple(_round(ent.get(c), ndigits) for c in (10, 20, 30))
        b = tuple(_round(ent.get(c), ndigits) for c in (11, 21, 31))
        first, second = sorted([a, b])
        return (ent.type, first, second)
    out = [ent.type]
    for code in codes:
        v = ent.get(code)
        if code in (1, 2):
            out.append(v)
        else:
            out.append(_round(v, ndigits))
    return tuple(out)


def find_duplicates(doc: Document) -> Dict[str, object]:
    """返回 {groups: [[handle...]], count, removable}。

    `removable` 每组除最小句柄外都应可删（这里只报告，不动手）。
    """
    buckets: Dict[Tuple, List[Entity]] = defaultdict(list)
    for ent in doc.entities():
        key = geo_key(ent)
        if key is None:
            continue
        buckets[key].append(ent)

    groups: List[List[str]] = []
    removable: List[str] = []
    for key, ents in buckets.items():
        if len(ents) < 2:
            continue
        handles = sorted(e.handle or "" for e in ents)
        groups.append(handles)
        removable.extend(handles[1:])
    return {"groups": groups, "count": len(groups), "removable": removable}


def find_unused(doc: Document) -> Dict[str, object]:
    """未被引用的图层 / 线型 / 块定义。图层 "0" 永远保留。"""
    ents = doc.entities()

    used_layers = {e.layer or "0" for e in ents}
    used_linetypes = set()
    used_blocks = {e.get(2) for e in ents if e.type == "INSERT" and e.get(2)}

    tables = doc.sections.get("TABLES") or []
    declared_layers, declared_lt, declared_blocks = set(), set(), set()
    blocks_section = doc.sections.get("BLOCKS") or []

    cur_table = None
    for code, value in tables:
        if code == 0 and value == "TABLE":
            cur_table = None
        elif code == 2 and value in ("LAYER", "LTYPE"):
            cur_table = value
        elif code == 0 and value == "ENDTAB":
            cur_table = None
        elif code == 0 and cur_table == "LAYER":
            pass
        elif code == 2 and cur_table == "LAYER":
            declared_layers.add(value)
        elif code == 6:
            used_linetypes.add(value)
        elif code == 3 and cur_table == "LTYPE":
            declared_lt.add(value)

    for i, (code, value) in enumerate(blocks_section):
        if code == 2:
            declared_blocks.add(value)

    unused_layers = sorted(declared_layers - used_layers - {"0"})
    unused_blocks = sorted(declared_blocks - used_blocks
                           - {"*Model_Space", "*Paper_Space", "*Paper_Space0"})
    unused_linetypes = sorted(declared_lt - used_linetypes - {"Continuous", "BYLAYER",
                                                              "BYBLOCK"})
    return {"layers": unused_layers, "linetypes": unused_linetypes,
            "blocks": unused_blocks,
            "count": len(unused_layers) + len(unused_blocks) + len(unused_linetypes)}


def overlaps(a: Entity, b: Entity, tol: float = 1e-6) -> bool:
    """两条 LINE 是否几乎重合（含反向）。"""
    if a.type != "LINE" or b.type != "LINE":
        return False
    pa, qa = a.point(), None
    xs, ys = a.floats(11), a.floats(21)
    if not pa or not xs or not ys:
        return False
    qa = (xs[0], ys[0], 0.0)
    pb, xs2, ys2 = b.point(), b.floats(11), b.floats(21)
    if not pb or not xs2 or not ys2:
        return False
    qb = (xs2[0], ys2[0], 0.0)

    def near(p, q):
        return math.dist(p[:2], q[:2]) <= tol

    return (near(pa, pb) and near(qa, qb)) or (near(pa, qb) and near(qa, pb))
