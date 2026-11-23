"""用 gmsh 划体积网格（四面体），供 ccx 求解。

为什么自己写 .inp 而不用 gmsh 的 Abaqus 导出：我们需要**按几何位置**圈出约束面与
加载面（x≈0 / x≈L），自己做才控制得住节点集编号；gmsh 的 inp 里还会混进线/三角面组，
真跑起来更容易出错。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]


class FeaError(RuntimeError):
    pass


def gmsh_version() -> Optional[str]:
    try:
        import gmsh
    except Exception:                                     # noqa: BLE001
        return None
    return getattr(gmsh, "__version__", "?")


@dataclass
class TetMesh:
    """节点 id → 坐标；四面体 → 4 个节点 id（gmsh 编号与 C3D4 约定一致）。"""

    nodes: Dict[int, Vec3]
    tets: List[Tuple[int, int, int, int]]          # 只用 4 个角点（体积/质量用）
    source: str = ""
    order: int = 1                                  # 1=C3D4, 2=C3D10
    tets10: List[Tuple[int, ...]] = field(default_factory=list)   # 10 节点连接（gmsh 序）

    def bbox(self) -> Dict[str, float]:
        xs = [p[0] for p in self.nodes.values()]
        ys = [p[1] for p in self.nodes.values()]
        zs = [p[2] for p in self.nodes.values()]
        return {"xmin": min(xs), "xmax": max(xs), "ymin": min(ys), "ymax": max(ys),
                "zmin": min(zs), "zmax": max(zs)}

    def select(self, pred: Callable[[Vec3], bool]) -> List[int]:
        return sorted(nid for nid, p in self.nodes.items() if pred(p))

    def volume(self) -> float:
        """网格体积（各四面体体积求和）——与几何体积对账用。"""
        total = 0.0
        for a, b, c, d in self.tets:
            total += _tet_volume(self.nodes[a], self.nodes[b], self.nodes[c], self.nodes[d])
        return total

    def inverted(self) -> List[Tuple[int, int, int, int]]:
        """负体积四面体（网格质量硬伤）。"""
        out = []
        for tet in self.tets:
            v = _tet_volume(*(self.nodes[n] for n in tet))
            if v <= 0:
                out.append(tet)
        return out

    def surface_triangles(self, pred: Callable[[Vec3], bool]) -> List[Tuple[int, int, int]]:
        """三个节点都满足 pred 的表面三角形（用于把面载荷化成节点一致载荷）。"""
        keep = set(self.select(pred))
        return [t for t in self._triangles() if t[0] in keep and t[1] in keep and t[2] in keep]

    def _triangles(self) -> List[Tuple[int, int, int]]:
        # 从四面体抽出 4 个面并去重（同一条面被两个体共享只算一次）
        seen = set()
        out: List[Tuple[int, int, int]] = []
        for a, b, c, d in self.tets:
            for tri in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
                key = tuple(sorted(tri))
                if key in seen:
                    continue
                seen.add(key)
                out.append((a, b, c) if key == tuple(sorted((a, b, c))) else
                           (a, b, d) if key == tuple(sorted((a, b, d))) else
                           (a, c, d) if key == tuple(sorted((a, c, d))) else (b, c, d))
        return out

    def tri_area(self, tri: Tuple[int, int, int]) -> float:
        return _tri_area(self.nodes[tri[0]], self.nodes[tri[1]], self.nodes[tri[2]])

    def summary(self) -> Dict[str, object]:
        return {"nodes": len(self.nodes), "tets": len(self.tets),
                "volume": round(self.volume(), 6),
                "inverted": len(self.inverted()), "bbox": self.bbox(),
                "source": self.source}


def _tri_area(a: Vec3, b: Vec3, c: Vec3) -> float:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def _tet_volume(a: Vec3, b: Vec3, c: Vec3, d: Vec3) -> float:
    """有符号体积 ×6 的 1/6（正 = 右手系）。"""
    ax, ay, az = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    bx, by, bz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cx, cy, cz = d[0] - a[0], d[1] - a[1], d[2] - a[2]
    det = (ax * (by * cz - bz * cy)
           - ay * (bx * cz - bz * cx)
           + az * (bx * cy - by * cx))
    return det / 6.0


def _positive(v: float, name: str) -> float:
    x = float(v)
    if x != x or abs(x) == float("inf") or x <= 0:
        raise FeaError("%s 必须是有限正数：%r" % (name, v))
    return x


def _collect(order: int, node_tags, coords, types, node_sets) -> Tuple[Dict[int, Vec3], List, List]:
    nodes: Dict[int, Vec3] = {}
    for i, tag in enumerate(node_tags):
        nodes[int(tag)] = (float(coords[3 * i]), float(coords[3 * i + 1]),
                           float(coords[3 * i + 2]))
    corners: List[Tuple[int, int, int, int]] = []
    full: List[Tuple[int, ...]] = []
    want = 4 if order == 1 else 11            # gmsh: 4=tet4, 11=tet10
    for etype, ntags in zip(types, node_sets):
        if int(etype) != want:
            raise FeaError("单元类型不符：期望 %d，得到 %s（order=%d）" % (want, etype, order))
        flat = [int(n) for n in ntags]
        per = 4 if order == 1 else 10
        for k in range(0, len(flat), per):
            chunk = tuple(flat[k:k + per])
            corners.append(chunk[:4])
            full.append(chunk)
    return nodes, corners, full


def box_mesh(sx: float, sy: float, sz: float, *, mesh_size: float,
             origin: Vec3 = (0.0, 0.0, 0.0), name: str = "box",
             order: int = 1) -> TetMesh:
    """长方体四面体网格。原点在角点，沿 +X/+Y/+Z 延伸。"""
    import gmsh

    sx, sy, sz = _positive(sx, "sx"), _positive(sy, "sy"), _positive(sz, "sz")
    h = _positive(mesh_size, "mesh_size")
    ox, oy, oz = (float(v) for v in origin)

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add(name)
        gmsh.model.occ.addBox(ox, oy, oz, sx, sy, sz)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", h)
        gmsh.option.setNumber("Mesh.MeshSizeMin", h * 0.4)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", h)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", h * 0.4)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.option.setNumber("Mesh.ElementOrder", 2 if order == 2 else 1)
        gmsh.model.mesh.generate(3)
        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        types, _, node_sets = gmsh.model.mesh.getElements(3)
        nodes, corners, full = _collect(order, node_tags, coords, types, node_sets)
        if not corners:
            raise FeaError("没有生成体单元（mesh_size=%r 可能太大或几何有问题）" % mesh_size)
        return TetMesh(nodes=nodes, tets=corners, order=order, tets10=full,
                       source="gmsh box %gx%gx%g order=%d" % (sx, sy, sz, order))
    finally:
        gmsh.finalize()


def cylinder_mesh(radius: float, length: float, *, mesh_size: float,
                  axis: str = "z", name: str = "cyl", order: int = 1) -> TetMesh:
    """圆柱（沿指定轴），用于轴类件。"""
    import gmsh

    r = _positive(radius, "radius")
    L = _positive(length, "length")
    h = _positive(mesh_size, "mesh_size")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add(name)
        if axis == "z":
            gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, L, r)
        elif axis == "x":
            gmsh.model.occ.addCylinder(0, 0, 0, L, 0, 0, r)
        else:
            raise FeaError("axis 只支持 x / z")
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", h)
        gmsh.option.setNumber("Mesh.ElementOrder", 2 if order == 2 else 1)
        gmsh.model.mesh.generate(3)
        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        types, _, node_sets = gmsh.model.mesh.getElements(3)
        nodes, corners, full = _collect(order, node_tags, coords, types, node_sets)
        if not corners:
            raise FeaError("没有生成体单元")
        return TetMesh(nodes=nodes, tets=corners, order=order, tets10=full,
                       source="gmsh cylinder r=%g L=%g %s order=%d" % (r, L, axis, order))
    finally:
        gmsh.finalize()
