"""关联标注的几何关联模型（数据模型参照 CADCraft `crates/engine/assoc.rs`）。

`dim.associative` 卡在"AutoCAD 不让我们建关联标注"。要往下走，先得说清
**"关联"到底记了什么**——这个模块就是那份定义：

* 一条标注引用两个**几何锚点**（哪条实体、哪个子元素：端点/中点/圆心/整条）；
* 标注值不是自由的数，而是**由锚点算出来的**；
* 被引用的几何一改，标注要能重算（`recompute`）并能判断"过期"（`stale`）。

这样一来，即使 AutoCAD 侧建不了真关联标注，我们也能：
1. 记录关联关系 → 2. 检测过期 → 3. 删掉旧标注、按新值重建（我们已有的 `dim.update` 路线）。
这就是"关联语义"的最小可用实现。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Point3 = Tuple[float, float, float]

ANCHORS = ("endpoint", "endpoint2", "midpoint", "center", "whole")


class AssocError(ValueError):
    pass


@dataclass(frozen=True)
class Anchor:
    """一个几何锚点：实体句柄 + 子元素语义。"""

    entity: str
    kind: str = "endpoint"          # endpoint/endpoint2/midpoint/center/whole
    index: int = 0                  # 多段线等"第几个顶点"

    def __post_init__(self) -> None:
        if self.kind not in ANCHORS:
            raise AssocError("未知锚点类型：%r（可用：%s）"
                             % (self.kind, ", ".join(ANCHORS)))


@dataclass
class AssocDimension:
    """一条关联标注：两个锚点 + 由锚点算出的值。"""

    handle: str
    anchors: Tuple[Anchor, Anchor]
    measurement: float
    style: Optional[str] = None
    note: str = ""

    def recompute(self, entities: Dict[str, object]) -> float:
        p1 = resolve_point(entities, self.anchors[0])
        p2 = resolve_point(entities, self.anchors[1])
        return math.dist(p1[:2], p2[:2])

    def stale(self, entities: Dict[str, object], tol: float = 1e-6) -> bool:
        try:
            return abs(self.recompute(entities) - self.measurement) > tol
        except AssocError:
            return True                  # 引用的实体没了 → 也算过期


def _xy(p: Sequence[float]) -> Point3:
    if len(p) >= 3:
        return (float(p[0]), float(p[1]), float(p[2]))
    return (float(p[0]), float(p[1]), 0.0)


def _entity_point(ent: object) -> Point3:
    point = ent.point()                                  # type: ignore[attr-defined]
    if point is None:
        raise AssocError("%s 没有可用坐标" % getattr(ent, "type", "?"))
    return _xy(point)


def _entity_point2(ent: object) -> Point3:
    xs = ent.floats(11)                                   # type: ignore[attr-defined]
    ys = ent.floats(21)                                   # type: ignore[attr-defined]
    if not xs or not ys:
        raise AssocError("%s 没有第二点（组码 11/21）" % getattr(ent, "type", "?"))
    return (xs[0], ys[0], 0.0)


def resolve_point(entities: Dict[str, object], anchor: Anchor) -> Point3:
    """把锚点解析成坐标。实体不在 → AssocError（明确失败，不返回 None）。"""
    ent = entities.get(anchor.entity)
    if ent is None:
        raise AssocError("引用的实体不存在：%s" % anchor.entity)
    etype = getattr(ent, "type", "")
    if anchor.kind == "endpoint":
        if etype == "CIRCLE":
            raise AssocError("圆没有端点，请用 center")
        return _entity_point(ent)
    if anchor.kind == "endpoint2":
        if etype not in ("LINE", "LWPOLYLINE"):
            raise AssocError("%s 没有第二端点" % etype)
        return _entity_point2(ent)
    if anchor.kind == "midpoint":
        if etype != "LINE":
            raise AssocError("中点只支持 LINE（%s 请用端点）" % etype)
        a, b = _entity_point(ent), _entity_point2(ent)
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0.0)
    if anchor.kind == "center":
        if etype not in ("CIRCLE", "ARC"):
            raise AssocError("%s 没有圆心" % etype)
        return _entity_point(ent)
    # whole：用实体起点（对圆是圆心）
    return _entity_point(ent)


def create(handle: str, entities: Dict[str, object],
           a: Anchor, b: Anchor, *, style: Optional[str] = None) -> AssocDimension:
    """按两个锚点建一条关联标注（值由当前几何算出）。"""
    p1 = resolve_point(entities, a)
    p2 = resolve_point(entities, b)
    return AssocDimension(handle=handle, anchors=(a, b),
                          measurement=math.dist(p1[:2], p2[:2]), style=style)


def scan_stale(dims: Sequence[AssocDimension],
               entities: Dict[str, object], tol: float = 1e-6) -> List[dict]:
    """批量检查哪些标注过期（几何改了但标注没更新）。"""
    out: List[dict] = []
    for d in dims:
        try:
            now = d.recompute(entities)
        except AssocError as exc:
            out.append({"handle": d.handle, "reason": "unresolved", "detail": str(exc)})
            continue
        if abs(now - d.measurement) > tol:
            out.append({"handle": d.handle, "reason": "stale",
                        "recorded": d.measurement, "current": now})
    return out
