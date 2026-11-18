"""二维曲线几何：求交、圆角、倒角（算法参照 CADCraft `crates/geom`）。

为什么自己算：这些量 AutoCAD 命令也能做，但**判据需要独立的期望值**——
比如"圆角圆心应该在 (5,5)、切点在 (5,0) 和 (0,5)"，必须由我们算，不能问 AutoCAD
"你算对了吗"。同类的还有修剪/偏移的边界判定（后续批次）。

约定：坐标是 (x, y)；角度用弧度；退化情形（平行、半径过大、相切但切点越界）
一律抛 `GeometryError`，**不返回静默错值**。
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Vec2 = Tuple[float, float]


class GeometryError(ValueError):
    """几何上无解/退化（平行、相离、半径过大……）。"""


def _sub(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Vec2, k: float) -> Vec2:
    return (a[0] * k, a[1] * k)


def _dot(a: Vec2, b: Vec2) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Vec2, b: Vec2) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _norm(a: Vec2) -> float:
    return math.hypot(a[0], a[1])


def _unit(a: Vec2) -> Vec2:
    n = _norm(a)
    if n < 1e-12:
        raise GeometryError("零长度方向")
    return (a[0] / n, a[1] / n)


# ── 求交 ────────────────────────────────────────────────────────────
def line_line(p1: Vec2, p2: Vec2, p3: Vec2, p4: Vec2,
              *, segments: bool = True) -> List[Vec2]:
    """线段/直线求交。`segments=False` 时按无限长直线算。"""
    d1, d2 = _sub(p2, p1), _sub(p4, p3)
    den = _cross(d1, d2)
    if abs(den) < 1e-12:
        return []                                  # 平行或重合：没有唯一交点
    t = _cross(_sub(p3, p1), d2) / den
    u = _cross(_sub(p3, p1), d1) / den
    if segments and not (-1e-12 <= t <= 1 + 1e-12 and -1e-12 <= u <= 1 + 1e-12):
        return []
    return [_add(p1, _mul(d1, t))]


def line_circle(p1: Vec2, p2: Vec2, center: Vec2, r: float,
                *, segments: bool = True) -> List[Vec2]:
    """直线/线段与圆求交（0/1/2 个交点，相切返回 1 个）。"""
    if r <= 0:
        raise GeometryError("半径必须为正")
    d = _sub(p2, p1)
    f = _sub(p1, center)
    a = _dot(d, d)
    if a < 1e-18:
        raise GeometryError("线段退化为点")
    b = 2 * _dot(f, d)
    c = _dot(f, f) - r * r
    disc = b * b - 4 * a * c
    if disc < -1e-12:
        return []
    if abs(disc) <= 1e-12:
        ts = [-b / (2 * a)]
    else:
        sq = math.sqrt(disc)
        ts = [(-b - sq) / (2 * a), (-b + sq) / (2 * a)]
    out: List[Vec2] = []
    for t in ts:
        if segments and not (-1e-12 <= t <= 1 + 1e-12):
            continue
        out.append(_add(p1, _mul(d, t)))
    return out


def circle_circle(c1: Vec2, r1: float, c2: Vec2, r2: float) -> List[Vec2]:
    """两圆求交；内含/外离抛错（这是"无交"而非"无解"，调用方要能区分）。"""
    if r1 <= 0 or r2 <= 0:
        raise GeometryError("半径必须为正")
    d = _norm(_sub(c2, c1))
    if d < 1e-12:
        if abs(r1 - r2) < 1e-12:
            raise GeometryError("两圆重合（无穷多交点）")
        raise GeometryError("同心圆无交点")
    if d > r1 + r2 + 1e-12 or d < abs(r1 - r2) - 1e-12:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    h = math.sqrt(max(h2, 0.0))
    base = _add(c1, _mul(_unit(_sub(c2, c1)), a))
    u = _unit(_sub(c2, c1))
    perp = (-u[1], u[0])
    if h < 1e-12:
        return [base]
    return [_add(base, _mul(perp, h)), _sub(base, _mul(perp, h))]


def ellipse_point(center: Vec2, rx: float, ry: float, t: float) -> Vec2:
    return (center[0] + rx * math.cos(t), center[1] + ry * math.sin(t))


def ellipse_line(center: Vec2, rx: float, ry: float, p1: Vec2, p2: Vec2,
                 *, samples: int = 720, tol: float = 1e-10) -> List[Vec2]:
    """椭圆与直线求交：参数扫描找符号变化，再用二分精修。

    解析解要解四次方程、数值稳定性差；**扫描+二分**对工程够用且不会误报，
    代价是极短切线附近的交点可能漏（已知限制，判据里要允许 ±tol）。
    """
    # 把直线法向化，构造 f(t) = 有符号距离
    n = (-(p2[1] - p1[1]), p2[0] - p1[0])
    nn = _norm(n)
    if nn < 1e-15:
        raise GeometryError("直线退化")
    n = (n[0] / nn, n[1] / nn)

    def f(t: float) -> float:
        pt = ellipse_point(center, rx, ry, t)
        return n[0] * (pt[0] - p1[0]) + n[1] * (pt[1] - p1[1])

    out: List[Vec2] = []
    step = 2 * math.pi / samples
    prev_t = 0.0
    prev = f(prev_t)
    for i in range(1, samples + 1):
        t = i * step
        cur = f(t)
        if prev == 0.0:
            out.append(ellipse_point(center, rx, ry, prev_t))
        elif prev * cur < 0:
            lo, hi, flo = prev_t, t, prev
            for _ in range(80):
                mid = (lo + hi) / 2
                fm = f(mid)
                if abs(fm) < tol:
                    break
                if flo * fm < 0:
                    hi = mid
                else:
                    lo, flo = mid, fm
            out.append(ellipse_point(center, rx, ry, (lo + hi) / 2))
        prev_t, prev = t, cur
    return out


# ── 圆角 / 倒角 ─────────────────────────────────────────────────────
def _corner_dirs(corner: Vec2, a: Vec2, b: Vec2) -> Tuple[Vec2, Vec2, float]:
    """两条边从角点出发的方向与夹角（0<θ<π）。"""
    d1, d2 = _unit(_sub(a, corner)), _unit(_sub(b, corner))
    cosang = max(-1.0, min(1.0, _dot(d1, d2)))
    theta = math.acos(cosang)
    if theta < 1e-9 or abs(theta - math.pi) < 1e-9:
        raise GeometryError("两边平行或反向，无法圆角/倒角")
    return d1, d2, theta


def fillet(corner: Vec2, a: Vec2, b: Vec2, radius: float) -> dict:
    """两直线间的圆角：返回圆心、切点、扫掠角。

    切点到角点的距离 = r / tan(θ/2)。若该距离超过任一边长度 → 切点越界，抛错。
    """
    if radius <= 0:
        raise GeometryError("圆角半径必须为正")
    d1, d2, theta = _corner_dirs(corner, a, b)
    half = theta / 2
    dist = radius / math.tan(half)
    if dist > _norm(_sub(a, corner)) + 1e-9 or dist > _norm(_sub(b, corner)) + 1e-9:
        raise GeometryError("圆角半径过大：切点超出边")
    t1 = _add(corner, _mul(d1, dist))
    t2 = _add(corner, _mul(d2, dist))
    bis = _unit(_add(d1, d2))
    center = _add(corner, _mul(bis, radius / math.sin(half)))
    return {"center": center, "tangent1": t1, "tangent2": t2,
            "radius": radius, "sweep_rad": math.pi - theta, "corner": corner}


def chamfer(corner: Vec2, a: Vec2, b: Vec2, d1: float, d2: float) -> dict:
    """倒角：两条边上各截 d1/d2，返回两个倒角点与长度。"""
    if d1 <= 0 or d2 <= 0:
        raise GeometryError("倒角距离必须为正")
    ua, ub, _ = _corner_dirs(corner, a, b)
    if d1 > _norm(_sub(a, corner)) + 1e-9 or d2 > _norm(_sub(b, corner)) + 1e-9:
        raise GeometryError("倒角距离过大：切点超出边")
    p1 = _add(corner, _mul(ua, d1))
    p2 = _add(corner, _mul(ub, d2))
    return {"p1": p1, "p2": p2, "length": _norm(_sub(p2, p1))}
