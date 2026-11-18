"""阵列与快速标注的规划（语义参照 CADCraft `cmd/array.rs`、`cmd/annotate_qdim.rs`）。

这两个命令在 AutoCAD 里选项很多、坑也多（ARRAY 的"关联/矩形/路径"、QDIM 的
"连续/基线/并列"判断）。我们这边把**决策部分**抽出来离线算清楚：

* `rectangular` / `polar` / `along_path`：生成每个实例的变换（平移+旋转），
  参数非法就报错（行列为 0、间距为 0 但要多个实例等）；
* `plan_qdim`：把一串边归组成"连续标注"或"基线标注"，并给出尺寸线位置。

真正的绘图仍由 AutoCAD 做，但这些决策我们能自己验——判据才有独立期望值。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Vec2 = Tuple[float, float]


class ArrayError(ValueError):
    pass


@dataclass
class Instance:
    index: int
    dx: float
    dy: float
    rotation_deg: float = 0.0

    def apply(self, p: Vec2) -> Vec2:
        c, s = math.cos(math.radians(self.rotation_deg)), math.sin(math.radians(self.rotation_deg))
        return (p[0] * c - p[1] * s + self.dx, p[0] * s + p[1] * c + self.dy)


def rectangular(rows: int, cols: int, row_spacing: float, col_spacing: float) -> List[Instance]:
    """矩形阵列：行沿 +Y、列沿 +X。"""
    if rows < 1 or cols < 1:
        raise ArrayError("行列数必须 ≥1（收到 rows=%r, cols=%r）" % (rows, cols))
    if rows > 1 and row_spacing == 0:
        raise ArrayError("多行时行间距不能为 0")
    if cols > 1 and col_spacing == 0:
        raise ArrayError("多列时列间距不能为 0")
    out: List[Instance] = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            out.append(Instance(idx, c * float(col_spacing), r * float(row_spacing)))
            idx += 1
    return out


def polar(count: int, *, center: Vec2 = (0.0, 0.0), radius: float = 0.0,
          total_angle_deg: float = 360.0, rotate_items: bool = True) -> List[Instance]:
    """环形阵列：绕 center 均布。total=360 时首尾不重复。"""
    if count < 1:
        raise ArrayError("数量必须 ≥1")
    if count == 1:
        return [Instance(0, 0.0, 0.0)]
    step = total_angle_deg / (count if abs(total_angle_deg - 360.0) < 1e-9 else count - 1)
    out: List[Instance] = []
    for i in range(count):
        ang = math.radians(step * i)
        px = center[0] + radius * math.cos(ang)
        py = center[1] + radius * math.sin(ang)
        out.append(Instance(i, px, py, step * i if rotate_items else 0.0))
    return out


def along_path(points: Sequence[Vec2], count: int, *, closed: bool = False) -> List[Instance]:
    """沿折线等距布点：返回每个实例的平移（用折线分段线性插值）。"""
    if count < 2:
        raise ArrayError("沿路径阵列至少 2 个实例")
    if len(points) < 2:
        raise ArrayError("路径至少要 2 个点")
    seglens = [math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total = sum(seglens) + (math.dist(points[-1], points[0]) if closed else 0.0)
    if total <= 0:
        raise ArrayError("路径总长为 0")
    out: List[Instance] = []
    for k in range(count):
        d = total * k / (count if closed else count - 1)
        acc = 0.0
        pos: Optional[Vec2] = None
        for i, L in enumerate(seglens):
            if acc + L >= d - 1e-12:
                t = 0.0 if L == 0 else (d - acc) / L
                a, b = points[i], points[i + 1]
                pos = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                break
            acc += L
        if pos is None:                                # 落在闭合段上
            a, b = points[-1], points[0]
            rest = d - acc
            L = math.dist(b, a)
            t = 0.0 if L == 0 else rest / L
            pos = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        out.append(Instance(k, pos[0], pos[1]))
    return out


# ── 快速标注规划 ────────────────────────────────────────────────────
@dataclass
class DimPlan:
    kind: str                      # continuous | baseline
    segments: List[int]            # 参与的下标
    dim_line_y: float              # 尺寸线位置（水平组用 y，垂直组用 x）
    axis: str                      # horizontal | vertical

    def to_dict(self) -> dict:
        return {"kind": self.kind, "segments": list(self.segments),
                "dim_line_y": self.dim_line_y, "axis": self.axis}


def _axis_of(a: Vec2, b: Vec2, tol_deg: float = 0.5) -> Optional[str]:
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0
    if ang <= tol_deg or ang >= 180.0 - tol_deg:
        return "horizontal"
    if abs(ang - 90.0) <= tol_deg:
        return "vertical"
    return None


def plan_qdim(segments: Sequence[Tuple[Vec2, Vec2]], *, offset: float = 10.0,
              tol: float = 1e-6) -> List[DimPlan]:
    """把边归组成连续/基线标注。

    规则（可解释、可测）：
    * 先按方向分组（水平/垂直；斜边不参与 QDIM，返回空）；
    * 组内按起点坐标排序，**首尾相接**的连成一条 `continuous`；
    * 不相接但**投影起点相同**的，合成 `baseline`（基线标注）。
    """
    if offset <= 0:
        raise ArrayError("标注偏移必须为正")
    out: List[DimPlan] = []
    for axis in ("horizontal", "vertical"):
        items: List[Tuple[int, float, float, Tuple[Vec2, Vec2]]] = []
        for i, (a, b) in enumerate(segments):
            if _axis_of(a, b) != axis:
                continue
            start = a[0] if axis == "horizontal" else a[1]
            items.append((i, start, min(a[1], b[1]) if axis == "horizontal"
                          else min(a[0], b[0]), (a, b)))
        if not items:
            continue
        items.sort(key=lambda t: (t[1], t[2]))
        chain: List[int] = []
        chain_end: Optional[float] = None
        for idx, start, _low, (a, b) in items:
            end = max(a[0], b[0]) if axis == "horizontal" else max(a[1], b[1])
            if chain and chain_end is not None and abs(start - chain_end) <= tol:
                chain.append(idx)
                chain_end = end
                continue
            if len(chain) >= 2:
                base = min(chain_end - 0 if chain_end is not None else 0, 0)  # 占位
                out.append(DimPlan("continuous", list(chain),
                                   offset + _min_low(items, chain, axis), axis))
            chain, chain_end = [idx], end
        if len(chain) >= 2:
            out.append(DimPlan("continuous", list(chain),
                               offset + _min_low(items, chain, axis), axis))

    # 基线：同一"起点"的多条（不同长度）
    for axis in ("horizontal", "vertical"):
        groups: dict = {}
        for i, (a, b) in enumerate(segments):
            if _axis_of(a, b) != axis:
                continue
            key = round(a[0] if axis == "horizontal" else a[1], 9)
            groups.setdefault(key, []).append(i)
        for key, idxs in sorted(groups.items()):
            if len(idxs) >= 2:
                low = min((min(segments[i][0][1], segments[i][1][1]) if axis == "horizontal"
                           else min(segments[i][0][0], segments[i][1][0])) for i in idxs)
                out.append(DimPlan("baseline", sorted(idxs), offset + low, axis))
    return out


def _min_low(items, chain: Sequence[int], axis: str) -> float:
    lows = []
    for idx, _start, low, _seg in items:
        if idx in chain:
            lows.append(low)
    return min(lows) if lows else 0.0
