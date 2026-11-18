"""多边形：偏移、点包含、孤岛归属（算法参照 CADCraft `crates/geom`）。

为什么自己算：`OFFSET` 命令能让 AutoCAD 干活，但**判据需要独立期望值**——
"偏移 5 后面积应该是 2500"，这个数必须我们算。另外"偏移后自交"是经典坑，
命令会给出乱七八糟的结果而我们得能识别。

已知限制（写在这里，不藏着）：
* 只做**直线段**多边形；含 bulge 圆弧的多段线由 `bulge_to_points` 先离散再偏移
  （离散会带来微小误差，判据用容差接受）。
* 拐角默认 miter（尖角）；超过 miter 上限时退化为斜切，不生成圆弧过渡。
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Vec2 = Tuple[float, float]


class GeometryError(ValueError):
    """几何上无解（自交、退化、无法偏移……）。"""


def _sub(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] - b[0], a[1] - b[1])


def _norm(a: Vec2) -> float:
    return math.hypot(a[0], a[1])


def _unit(a: Vec2) -> Vec2:
    n = _norm(a)
    if n < 1e-12:
        raise GeometryError("零长度边")
    return (a[0] / n, a[1] / n)


def _cross(a: Vec2, b: Vec2) -> float:
    return a[0] * b[1] - a[1] * b[0]


def signed_area(poly: Sequence[Vec2]) -> float:
    """有符号面积（逆时针为正）。"""
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def area(poly: Sequence[Vec2]) -> float:
    return abs(signed_area(poly))


def point_in_polygon(pt: Vec2, poly: Sequence[Vec2]) -> bool:
    """射线法。边界上的点结果不保证（工程上可接受，判据不用边界点）。"""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xin:
                inside = not inside
    return inside


def bulge_to_points(p1: Vec2, p2: Vec2, bulge: float, *, steps: int = 16) -> List[Vec2]:
    """把一段带 bulge 的圆弧离散成折线（不含 p1，含 p2）。

    bulge = tan(θ/4)，正负表示凸向；|bulge| 越大弧越弯。
    """
    if abs(bulge) < 1e-12:
        return [p2]
    chord = _norm(_sub(p2, p1))
    if chord < 1e-12:
        raise GeometryError("圆弧弦长为 0")
    theta = 4.0 * math.atan(bulge)
    # 圆心：弦中点沿法向偏移 sagitta 相关距离
    mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    u = _unit(_sub(p2, p1))
    nrm = (-u[1], u[0])
    half = abs(theta) / 2
    sag = (chord / 2) / math.tan(half) if abs(math.tan(half)) > 1e-12 else 0.0
    sign = 1.0 if theta > 0 else -1.0
    center = (mid[0] + nrm[0] * sag * sign, mid[1] + nrm[1] * sag * sign)
    r = _norm(_sub(p1, center))
    a0 = math.atan2(p1[1] - center[1], p1[0] - center[0])
    out: List[Vec2] = []
    for k in range(1, steps + 1):
        a = a0 + theta * k / steps
        out.append((center[0] + r * math.cos(a), center[1] + r * math.sin(a)))
    out[-1] = p2                             # 端点务必精确
    return out


def _seg_intersect(a1: Vec2, a2: Vec2, b1: Vec2, b2: Vec2) -> bool:
    def orient(p: Vec2, q: Vec2, r: Vec2) -> float:
        return _cross(_sub(q, p), _sub(r, p))

    d1 = orient(b1, b2, a1)
    d2 = orient(b1, b2, a2)
    d3 = orient(a1, a2, b1)
    d4 = orient(a1, a2, b2)
    return ((d1 > 1e-12) != (d2 > 1e-12)) and ((d3 > 1e-12) != (d4 > 1e-12))


def _self_intersects(poly: Sequence[Vec2]) -> Optional[Tuple[int, int]]:
    n = len(poly)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _seg_intersect(poly[i], poly[(i + 1) % n],
                              poly[j], poly[(j + 1) % n]):
                return (i, j)
    return None


def _dist_point_segment(p: Vec2, a: Vec2, b: Vec2) -> float:
    ab = _sub(b, a)
    L2 = ab[0] * ab[0] + ab[1] * ab[1]
    if L2 < 1e-18:
        return _norm(_sub(p, a))
    ap = _sub(p, a)
    t = max(0.0, min(1.0, (ap[0] * ab[0] + ap[1] * ab[1]) / L2))
    proj = (a[0] + ab[0] * t, a[1] + ab[1] * t)
    return _norm(_sub(p, proj))


def _inradius_estimate(poly: Sequence[Vec2]) -> float:
    """内接圆半径的粗估：重心到各边的最短距离（凸多边形即精确）。"""
    n = len(poly)
    cx = sum(p[0] for p in poly) / n
    cy = sum(p[1] for p in poly) / n
    return min(_dist_point_segment((cx, cy), poly[i], poly[(i + 1) % n])
               for i in range(n))


def offset_polygon(poly: Sequence[Vec2], distance: float, *,
                   closed: bool = True, miter_limit: float = 4.0,
                   check_self_intersection: bool = True) -> List[Vec2]:
    """把多边形整体外扩（distance>0）/内缩（<0），拐角用 miter。

    方向由**有符号面积**决定：逆时针时"外"在左法向。这样同一个 distance
    对不同绕向都能得到"变大/变小"的一致含义。
    """
    if abs(distance) < 1e-15:
        raise GeometryError("偏移距离为 0")
    pts = list(poly)
    if closed and pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    if n < 3:
        raise GeometryError("至少需要 3 个点")

    if distance < 0:
        # 内缩超过内接圆半径 → 几何上无效。实测：40×40 内缩 25 时，
        # miter 会给出一个"跑到另一侧"的合法小方块（既不翻转也不自交），
        # 所以必须在算之前用内接圆半径拦掉。
        rin = _inradius_estimate(pts)
        if abs(distance) > rin + 1e-9:
            raise GeometryError("内缩超过内接圆半径 %.3g（偏移无效）" % rin)

    ccw = signed_area(pts) > 0
    # 外扩方向：逆时针取左法向，顺时针取右法向
    out: List[Vec2] = []
    for i in range(n):
        prev_pt = pts[(i - 1) % n] if closed or i > 0 else None
        cur = pts[i]
        nxt = pts[(i + 1) % n] if closed or i < n - 1 else None

        def offset_dir(a: Vec2, b: Vec2) -> Vec2:
            # 逆时针多边形的**内部在左**，所以"向外"是右法向 (u_y, -u_x)；
            # 顺时针反之。distance>0 表示向外，<0 表示向内。
            u = _unit(_sub(b, a))
            right = (u[1], -u[0])
            return right if ccw else (-right[0], -right[1])

        if prev_pt is None:                       # 开放折线起点
            d = offset_dir(cur, nxt)
            out.append((cur[0] + d[0] * distance, cur[1] + d[1] * distance))
            continue
        if nxt is None:                           # 开放折线终点
            d = offset_dir(prev_pt, cur)
            out.append((cur[0] + d[0] * distance, cur[1] + d[1] * distance))
            continue

        d1 = offset_dir(prev_pt, cur)
        d2 = offset_dir(cur, nxt)
        # 两条偏移线的交点 = miter 顶点
        p1 = (cur[0] + d1[0] * distance, cur[1] + d1[1] * distance)
        p2 = (cur[0] + d2[0] * distance, cur[1] + d2[1] * distance)
        u1 = _unit(_sub(cur, prev_pt))
        u2 = _unit(_sub(nxt, cur))
        den = _cross(u1, u2)
        if abs(den) < 1e-12:
            out.append(p1)                        # 共线：直接用
            continue
        t = _cross(_sub(p2, p1), u2) / den
        miter = (p1[0] + u1[0] * t, p1[1] + u1[1] * t)
        # miter 过长（很尖的角）→ 退化为两点斜切
        if _norm(_sub(miter, cur)) > abs(distance) * miter_limit:
            out.extend([p1, p2])
        else:
            out.append(miter)
    if closed and check_self_intersection:
        # 内缩过度时多边形**不会自交，而是绕向翻转**（顶点越过中心）。
        # 实测：40×40 内缩 25 → 顶点变成 (25,25)…(15,15)，仍是合法四边形但方向反了。
        if signed_area(pts) * signed_area(out) < 0:
            raise GeometryError("偏移导致多边形翻转（内缩过度），需清理")
        hit = _self_intersects(out)
        if hit is not None:
            raise GeometryError("偏移后自交（边 %d 与 %d 相交），需清理" % hit)
    return out


def classify_islands(polys: Sequence[Sequence[Vec2]]) -> List[dict]:
    """按包含关系给多边形分层：depth 偶数=实体，奇数=孔。

    返回 [{index, depth, area, is_hole}]，顺序与输入一致。
    """
    out: List[dict] = []
    for i, poly in enumerate(polys):
        depth = 0
        probe = poly[0]
        for j, other in enumerate(polys):
            if i == j:
                continue
            if point_in_polygon(probe, other) and area(other) > area(poly):
                depth += 1
        out.append({"index": i, "depth": depth, "area": area(poly),
                    "is_hole": depth % 2 == 1})
    return out


def hatch_area(polys: Sequence[Sequence[Vec2]]) -> float:
    """填充净面积 = 实体层面积 − 孔层面积。"""
    total = 0.0
    for meta in classify_islands(polys):
        total += -meta["area"] if meta["is_hole"] else meta["area"]
    return total
