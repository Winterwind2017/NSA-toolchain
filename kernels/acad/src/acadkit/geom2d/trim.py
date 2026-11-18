"""修剪与延伸的几何判定（参照 CADCraft `crates/geom` 的 trim/extend）。

AutoCAD 的 `TRIM`/`EXTEND` 命令能干活，但命令行方式在双文档下容易卡在"选择对象"
提示上；更关键的是**判据需要独立期望值**——"修剪后应该是 40..100"必须我们算。

本模块只做几何决策，不碰 COM：
* `cut_params`  求一条线段被若干"剪刀"切开的参数位置
* `trim_segment`  按保留侧裁剪（返回一段或两段）
* `extend_segment` 沿方向延长到最近的边界
边界支持线段与圆（圆用 `CircleCutter`）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Vec2 = Tuple[float, float]


class TrimError(ValueError):
    """没有交点/方向退化/延长找不到边界。"""


@dataclass
class CircleCutter:
    center: Vec2
    radius: float


def _sub(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Vec2, k: float) -> Vec2:
    return (a[0] * k, a[1] * k)


def _cross(a: Vec2, b: Vec2) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _norm(a: Vec2) -> float:
    return math.hypot(a[0], a[1])


def lerp(p1: Vec2, p2: Vec2, t: float) -> Vec2:
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


def cut_params(p1: Vec2, p2: Vec2,
               cutters: Sequence[object]) -> List[float]:
    """返回被切开的参数 t∈(0,1)，升序去重。

    `cutters` 支持 (a, b) 线段与 `CircleCutter`。
    """
    d = _sub(p2, p1)
    length2 = d[0] * d[0] + d[1] * d[1]
    if length2 < 1e-18:
        raise TrimError("线段退化为点")
    ts: List[float] = []
    for c in cutters:
        if isinstance(c, CircleCutter):
            f = _sub(p1, c.center)
            a = length2
            b = 2 * (f[0] * d[0] + f[1] * d[1])
            cc = f[0] * f[0] + f[1] * f[1] - c.radius * c.radius
            disc = b * b - 4 * a * cc
            if disc < -1e-12:
                continue
            if abs(disc) <= 1e-12:
                cand = [-b / (2 * a)]
            else:
                sq = math.sqrt(disc)
                cand = [(-b - sq) / (2 * a), (-b + sq) / (2 * a)]
        else:
            p3, p4 = c                              # type: ignore[misc]
            e = _sub(p4, p3)
            den = _cross(d, e)
            if abs(den) < 1e-12:
                continue
            t = _cross(_sub(p3, p1), e) / den
            u = _cross(_sub(p3, p1), d) / den
            if not (-1e-12 <= u <= 1 + 1e-12):
                continue                            # 交点在剪刀延长线上
            cand = [t]
        for t in cand:
            if 1e-9 < t < 1 - 1e-9:
                ts.append(t)
    ts.sort()
    out: List[float] = []
    for t in ts:
        if not out or abs(t - out[-1]) > 1e-9:
            out.append(t)
    return out


def trim_segment(p1: Vec2, p2: Vec2, cutters: Sequence[object], *,
                 keep: str = "start") -> List[Tuple[Vec2, Vec2]]:
    """按保留侧裁剪，返回裁剪后的线段列表。

    keep="start"  保留起点侧（从 p1 到**最近的**交点）
    keep="end"    保留终点侧
    keep="middle" 保留两个交点之间（至少需要 2 个交点）
    """
    ts = cut_params(p1, p2, cutters)
    if not ts:
        raise TrimError("没有交点，无法修剪")
    if keep == "start":
        return [(p1, lerp(p1, p2, ts[0]))]
    if keep == "end":
        return [(lerp(p1, p2, ts[-1]), p2)]
    if keep == "middle":
        if len(ts) < 2:
            raise TrimError("保留中段需要至少两个交点")
        return [(lerp(p1, p2, ts[0]), lerp(p1, p2, ts[-1]))]
    raise TrimError("未知保留方式：%r" % keep)


def extend_segment(p1: Vec2, p2: Vec2, boundary: Sequence[object], *,
                   which: str = "end", limit: float = 1e6) -> Tuple[Vec2, Vec2]:
    """把 p1→p2 沿方向延长到最近的边界；`which="start"` 反向延长。"""
    d = _sub(p2, p1)
    if _norm(d) < 1e-12:
        raise TrimError("线段退化为点")
    unit = (d[0] / _norm(d), d[1] / _norm(d))
    far = _add(p2, _mul(unit, limit)) if which == "end" else _sub(p1, _mul(unit, limit))
    near = p2 if which == "end" else p1
    ts = cut_params(near, far, boundary)
    if not ts:
        raise TrimError("延长方向没有边界")
    hit = lerp(near, far, ts[0])
    return (p1, hit) if which == "end" else (hit, p2)
