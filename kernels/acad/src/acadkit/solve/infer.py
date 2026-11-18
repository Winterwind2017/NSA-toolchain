"""从几何反推约束（对照 CADCraft `crates/constraints/auto.rs` 的思路）。

用途：拿到一张已有的图，自动判断哪两条边是水平的、哪两个点是重合的，
生成初始约束集——否则用户要一条条手点（AutoCAD 里这一步是"自动约束"）。

策略：全部基于容差比较，**只在证据充分时推断**，宁可少推断也不乱推断；
返回结果里带 `evidence`，让调用方知道每条约束是怎么来的。
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

from .constraints import Constraint, Point, Segment

Vec2 = Tuple[float, float]


def _angle_deg(a: Vec2, b: Vec2) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return math.degrees(math.atan2(dy, dx)) % 360.0


def _near_angle(angle: float, target: float, tol: float) -> bool:
    d = abs((angle - target + 180) % 360 - 180)
    return d <= tol


def infer_constraints(points: Dict[str, Point], segments: Dict[str, Segment], *,
                      angle_tol_deg: float = 0.5,
                      point_tol: float = 1e-6) -> List[dict]:
    """推断水平/垂直/共线（同向）/重合。

    返回 [{constraint, evidence, confidence}]，**不直接改图**。
    """
    out: List[dict] = []

    # 1) 水平 / 垂直
    for sid, seg in segments.items():
        a, b = points[seg.p1].xy, points[seg.p2].xy
        ang = _angle_deg(a, b)
        if _near_angle(ang, 0.0, angle_tol_deg) or _near_angle(ang, 180.0, angle_tol_deg):
            out.append({"constraint": Constraint("auto_h_%s" % sid, "horizontal",
                                                 points=(seg.p1, seg.p2)),
                        "evidence": "角度 %.3f° ≈ 0/180" % ang, "confidence": 1.0})
        elif _near_angle(ang, 90.0, angle_tol_deg) or _near_angle(ang, 270.0, angle_tol_deg):
            out.append({"constraint": Constraint("auto_v_%s" % sid, "vertical",
                                                 points=(seg.p1, seg.p2)),
                        "evidence": "角度 %.3f° ≈ 90/270" % ang, "confidence": 1.0})

    # 2) 重合点（不同 id 但坐标一致）
    ids = list(points)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            p, q = points[ids[i]].xy, points[ids[j]].xy
            if math.hypot(p[0] - q[0], p[1] - q[1]) <= point_tol:
                out.append({"constraint": Constraint(
                    "auto_coin_%s_%s" % (ids[i], ids[j]), "coincident",
                    points=(ids[i], ids[j])),
                    "evidence": "距离 %.3g ≤ %.3g" % (math.hypot(p[0] - q[0], p[1] - q[1]), point_tol),
                    "confidence": 1.0})

    # 3) 平行（同向）——只报置信度 0.8，因为"看起来平行"未必该约束
    seg_ids = list(segments)
    for i in range(len(seg_ids)):
        for j in range(i + 1, len(seg_ids)):
            s1, s2 = segments[seg_ids[i]], segments[seg_ids[j]]
            a1 = _angle_deg(points[s1.p1].xy, points[s1.p2].xy)
            a2 = _angle_deg(points[s2.p1].xy, points[s2.p2].xy)
            d = abs((a1 - a2 + 180) % 360 - 180)
            if d <= angle_tol_deg and not _near_angle(a1, 0, angle_tol_deg) \
                    and not _near_angle(a1, 90, angle_tol_deg):
                out.append({"constraint": Constraint(
                    "auto_par_%s_%s" % (seg_ids[i], seg_ids[j]), "parallel",
                    segments=(seg_ids[i], seg_ids[j])),
                    "evidence": "方向差 %.3f°" % d, "confidence": 0.8})

    return out


def apply_inferred(points: Dict[str, Point], segments: Dict[str, Segment],
                   inferred: Sequence[dict], *, min_confidence: float = 0.9) -> List[Constraint]:
    """把推断结果落到求解器可用的一组约束上（低置信度默认丢弃）。"""
    return [item["constraint"] for item in inferred
            if item["confidence"] >= min_confidence]
