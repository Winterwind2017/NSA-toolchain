"""离线 B-rep 建模与 STEP/STL 出口（用本机已有的 cadquery / OCP，不依赖 CAD 软件）。

为什么需要：所有"出几何"都开 AutoCAD/SolidWorks 有两个代价——**要许可证**、
**进不了 CI**。这一步给一个离线后端：参数化件 → 真 B-rep → STEP/STL，
体积/包围盒可与解析式逐项对账。

与 text-to-cad 的关系：思路借鉴（MIT），但**不引入 build123d**——本机已有
cadquery 2.8 + OCP 7.9，同一套 OpenCASCADE，少一个依赖。

约定：几何量一律 mm；`to_step` 返回实测值（字节数/面数/体积），方便当判据用。
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]


class BrepError(RuntimeError):
    """没有后端 / 参数非法 / 导出失败。"""


def backend() -> Optional[str]:
    """返回可用后端名（"cadquery"），不可用返回 None。"""
    try:
        import cadquery  # noqa: F401
    except Exception:                                    # noqa: BLE001
        return None
    return "cadquery"


def _cq():
    try:
        import cadquery as cq
    except Exception as exc:                             # noqa: BLE001
        raise BrepError("没有离线 B-rep 后端（需要 cadquery）: %s" % exc) from None
    return cq


def _positive(v: float, name: str) -> float:
    x = float(v)
    if x != x or abs(x) == float("inf") or x <= 0:
        raise BrepError("%s 必须是有限正数：%r" % (name, v))
    return x


# ── 参数化件 ────────────────────────────────────────────────────────
@dataclass
class Part:
    name: str
    obj: object                    # cadquery Workplane/Solid
    expected_volume: float         # 解析式算的期望体积（mm³）

    # ── 实测 ──
    def volume(self) -> float:
        return float(self.obj.val().Volume())

    def bbox(self) -> Dict[str, float]:
        b = self.obj.val().BoundingBox()
        return {"xlen": b.xlen, "ylen": b.ylen, "zlen": b.zlen,
                "xmin": b.xmin, "ymin": b.ymin, "zmin": b.zmin}

    def faces(self) -> int:
        return len(self.obj.val().Faces())

    def verify(self, rel_tol: float = 1e-6) -> Dict[str, object]:
        """体积与解析式对账——这是"几何对不对"的判据。"""
        got = self.volume()
        rel = abs(got - self.expected_volume) / max(self.expected_volume, 1e-12)
        return {"ok": rel <= rel_tol, "got": got,
                "expected": self.expected_volume, "relative_error": rel}


def shaft(diameter: float, length: float, *, name: str = "shaft") -> Part:
    """实心圆柱轴。"""
    d = _positive(diameter, "diameter")
    L = _positive(length, "length")
    cq = _cq()
    p = cq.Workplane("XY").circle(d / 2.0).extrude(L)
    return Part(name, p, math.pi * (d / 2.0) ** 2 * L)


def flange(outer_d: float, bore_d: float, thickness: float,
           bolt_holes: Sequence[Dict[str, float]] = (),
           *, name: str = "flange") -> Part:
    """法兰盘：外圆 - 内孔 - 螺栓孔。bolt_holes: [{diameter, bcd, count}]。"""
    D = _positive(outer_d, "outer_d")
    d = _positive(bore_d, "bore_d")
    t = _positive(thickness, "thickness")
    if d >= D:
        raise BrepError("内孔 %.2f 必须小于外径 %.2f" % (d, D))
    cq = _cq()
    p = cq.Workplane("XY").circle(D / 2.0).extrude(t)
    p = p.faces(">Z").workplane().hole(d)
    hole_volume = 0.0
    for i, hole in enumerate(bolt_holes):
        hd = _positive(hole.get("diameter", 0), "bolt[%d].diameter" % i)
        bcd = _positive(hole.get("bcd", 0), "bolt[%d].bcd" % i)
        count = int(hole.get("count", 0))
        if count < 1:
            raise BrepError("bolt[%d].count 必须 ≥1" % i)
        if bcd / 2.0 + hd / 2.0 > D / 2.0 - 1e-9:
            raise BrepError("螺栓孔超出外缘：bcd/2+hd/2 > D/2")
        p = p.faces(">Z").workplane().pushPoints(
            [(bcd / 2.0 * math.cos(2 * math.pi * k / count),
              bcd / 2.0 * math.sin(2 * math.pi * k / count)) for k in range(count)]
        ).hole(hd)
        hole_volume += count * math.pi * (hd / 2.0) ** 2 * t
    expected = (math.pi * (D / 2.0) ** 2 - math.pi * (d / 2.0) ** 2) * t - hole_volume
    return Part(name, p, expected)


def plate(length: float, width: float, thickness: float,
          holes: Sequence[Dict[str, float]] = (), *, name: str = "plate") -> Part:
    """平板：矩形 - 通孔。holes: [{x, y, diameter}]（以板中心为原点）。"""
    L = _positive(length, "length")
    W = _positive(width, "width")
    t = _positive(thickness, "thickness")
    cq = _cq()
    p = cq.Workplane("XY").box(L, W, t)
    hole_volume = 0.0
    for i, hole in enumerate(holes):
        hd = _positive(hole.get("diameter", 0), "hole[%d].diameter" % i)
        x = float(hole.get("x", 0.0))
        y = float(hole.get("y", 0.0))
        if abs(x) + hd / 2.0 > L / 2.0 + 1e-9 or abs(y) + hd / 2.0 > W / 2.0 + 1e-9:
            raise BrepError("孔 %d 超出板边" % i)
        p = p.faces(">Z").workplane().moveTo(x, y).hole(hd)
        hole_volume += math.pi * (hd / 2.0) ** 2 * t
    expected = L * W * t - hole_volume
    return Part(name, p, expected)


def stepped_shaft(segments, *, name: str = "stepped_shaft") -> Part:
    """阶梯轴：segments = [(diameter, length)]，从 z=0 往上依次堆。

    期望体积 = Σ π(d/2)²·L（解析式），便于与网格体积对账。
    """
    cq = _cq()
    if not segments:
        raise BrepError("segments 不能为空")
    p = None
    z = 0.0
    volume = 0.0
    for i, (d, length) in enumerate(segments):
        dd = _positive(d, "segments[%d].diameter" % i)
        L = _positive(length, "segments[%d].length" % i)
        if p is None:
            p = cq.Workplane("XY").circle(dd / 2.0).extrude(L)
        else:
            p = p.faces(">Z").workplane().circle(dd / 2.0).extrude(L)
        volume += math.pi * (dd / 2.0) ** 2 * L
        z += L
    return Part(name, p, volume)


def bracket(length: float, root_height: float, tip_height: float, width: float,
            *, name: str = "bracket") -> Part:
    """变截面角撑板（梯形侧影沿 Y 挤出）：根部高 root，端部高 tip（须 >0）。

    为什么端部不能为 0：尖角三角形在梁理论里 I→0、挠度积分发散，
    参考解不存在；工程上真实件也都有个小端面。
    """
    cq = _cq()
    L = _positive(length, "length")
    h0 = _positive(root_height, "root_height")
    h1 = _positive(tip_height, "tip_height")
    b = _positive(width, "width")
    if h1 >= h0:
        raise BrepError("tip_height 必须小于 root_height（否则不是收敛的变截面）")
    pts = [(0.0, 0.0), (L, 0.0), (L, h1), (0.0, h0)]
    p = cq.Workplane("XZ").polyline(pts).close().extrude(b)
    volume = (h0 + h1) / 2.0 * L * b
    return Part(name, p, volume)


# ── 导出 ────────────────────────────────────────────────────────────
def _export(part: Part, path: str, kind: str) -> Dict[str, object]:
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        raise BrepError("父目录不存在：%s" % d)
    cq = _cq()
    cq.exporters.export(part.obj, path, exportType=kind)
    if not os.path.isfile(path):
        raise BrepError("导出没有产出文件：%s（kind=%s）" % (path, kind))
    size = os.path.getsize(path)
    if size < 200:
        raise BrepError("导出文件过小（%d 字节），疑似空几何" % size)
    return {"path": path, "kind": kind, "bytes": size,
            "faces": part.faces(), "volume": part.volume()}


def to_step(part: Part, path: str) -> Dict[str, object]:
    return _export(part, path, "STEP")


def to_stl(part: Part, path: str, *, tolerance: float = 0.05) -> Dict[str, object]:
    info = _export(part, path, "STL")
    info["tolerance"] = tolerance
    return info


def read_step(path: str) -> Dict[str, object]:
    """把 STEP 读回来体积/面数——"文件是不是真几何"的判据。"""
    if not os.path.isfile(path):
        raise BrepError("文件不存在：%s" % path)
    cq = _cq()
    shape = cq.importers.importStep(path)
    solids = shape.solids().vals()
    if not solids:
        raise BrepError("STEP 读回没有实体：%s" % path)
    return {"solids": len(solids),
            "volume": sum(float(s.Volume()) for s in solids),
            "faces": sum(len(s.Faces()) for s in solids)}


def roundtrip(part: Part, path: str, *, rel_tol: float = 1e-3) -> Dict[str, object]:
    """建模 → STEP → 读回，体积必须一致。"""
    out = to_step(part, path)
    back = read_step(path)
    rel = abs(float(back["volume"]) - part.volume()) / max(part.volume(), 1e-12)
    return {"ok": rel <= rel_tol, "step": out, "back": back,
            "relative_error": rel, "expected_volume": part.volume()}
