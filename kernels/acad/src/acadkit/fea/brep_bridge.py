"""把 brep 造出来的零件直接送进 FEA：零件 → STEP → gmsh 划网格 → ccx。

为什么绕 STEP 一圈：gmsh 的 OCC 几何不能直接吃 cadquery 的内存对象，但能读 STEP；
顺带也验证了 `acadkit.brep` 的 STEP 出口**第三方内核真的能用**。

一条纪律：**网格体积必须与零件体积对得上**（默认 ≤5%）。圆柱类零件在粗网格下
内接多面体会少 8%~12% 体积，拿这种网格算出来的位移再准也没有意义（算的不是这个件）。
所以这里把 `volume_error` 当门禁，超了直接拒算。
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ..brep import parts as brep
from . import refs
from . import inp as inpmod
from .cases import solve_face_loaded
from .mesh import FeaError, TetMesh, step_mesh


@dataclass
class PartMesh:
    mesh: TetMesh
    step_path: str
    part_volume: float
    mesh_volume: float
    volume_error: float          # |mesh - part| / part

    def summary(self) -> Dict[str, object]:
        return {"nodes": len(self.mesh.nodes), "tets": len(self.mesh.tets),
                "order": self.mesh.order, "part_volume": round(self.part_volume, 3),
                "mesh_volume": round(self.mesh_volume, 3),
                "volume_error": round(self.volume_error, 6),
                "bbox": self.mesh.bbox(), "step": self.step_path}


def part_mesh(part: brep.Part, *, mesh_size: float, order: int = 2,
              workdir: Optional[str] = None, max_volume_error: float = 0.05,
              max_cells: int = 200_000) -> PartMesh:
    """零件 → STEP → 四面体网格，并校验体积保真度与**算力预算**。

    算力门禁：按包围盒体积粗估单元数（vol/h³），超过 `max_cells`（默认 20 万）
    直接拒绝。实测教训：200×100×0.8 的薄板用 h=0.4 会生成约 150 万四面体，
    ccx 跑 5 分钟不解（二阶后自由度 ~700 万），先把门禁放在前面比等超时好。
    """
    if not hasattr(part, "obj"):
        raise FeaError("part 需要是 acadkit.brep.parts.Part")
    bbox = part.bbox()
    vol_bbox = bbox["xlen"] * bbox["ylen"] * bbox["zlen"]
    est_cells = vol_bbox / max(mesh_size, 1e-9) ** 3
    if est_cells > max_cells:
        need = (vol_bbox / max_cells) ** (1.0 / 3.0)
        raise FeaError(
            "网格过大：h=%.3g mm 在包围盒 %.0f mm³ 上约 %.0f 万单元（上限 %d 万）。"
            "把 mesh_size 放大到 ≥ %.2f mm，或缩小零件/减薄方向单独建模"
            % (mesh_size, vol_bbox, est_cells / 1e4, max_cells // 10_000, need))
    workdir = workdir or tempfile.mkdtemp(prefix="brep_fea_")
    os.makedirs(workdir, exist_ok=True)
    step_path = os.path.join(workdir, "%s.step" % part.name)
    brep.to_step(part, step_path)
    mesh = step_mesh(step_path, mesh_size=mesh_size, order=order, name=part.name)

    part_volume = part.volume()
    mesh_volume = mesh.volume()
    err = abs(mesh_volume - part_volume) / part_volume if part_volume else float("inf")
    if err > max_volume_error:
        raise FeaError(
            "网格体积与零件差 %.2f%%（> %.0f%%），网格不忠实，拒算；"
            "把 mesh_size 减到 ≤ 最小特征尺寸/4 再试"
            % (err * 100, max_volume_error * 100))
    return PartMesh(mesh=mesh, step_path=step_path, part_volume=part_volume,
                    mesh_volume=mesh_volume, volume_error=err)


def _part_extents(part: brep.Part) -> Dict[str, float]:
    """零件包围盒三向尺寸（不划网格就能拿到）。"""
    b = part.bbox()
    return {"x": b["xlen"], "y": b["ylen"], "z": b["zlen"]}


def _axis_data(mesh: TetMesh, axis: str) -> Tuple[float, float, float]:
    idx = {"x": 0, "y": 1, "z": 2}[axis]
    coords = [p[idx] for p in mesh.nodes.values()]
    lo, hi = min(coords), max(coords)
    return lo, hi, hi - lo


def axial_part(part: brep.Part, *, force: float, E: float, nu: float,
               mesh_size: float, axis: str = "z", order: int = 2,
               tol: float = 3e-2, max_volume_error: float = 0.05,
               min_slenderness: float = 3.0,
               workdir: Optional[str] = None) -> Dict[str, object]:
    """零件受轴向拉力（默认 Z 向）。期望值用**网格有效截面积**（体积/长度）。

    前置判据：**细长比 L/√A ≥ 3**，否则一维杆公式不适用，直接拒绝。
    实测教训：法兰 Ø120×t10 的 L/√A≈0.10，圣维南衰减长度（~半径 60）远大于
    厚度 10，端部全约束会主导整个件，FE 给出顶面 uz 3.3e-5~8.1e-5 的严重非均匀场，
    与 FL/(EA) 差 63%——这不是算错，是公式不该用在这个件上。
    """
    # 先判细长比（用零件体积/包围盒，不划网格）——宽扁件不适用一维杆公式
    ext = _part_extents(part)
    length_geo = ext[axis]
    area_geo = part.volume() / length_geo if length_geo > 0 else 0.0
    slender_geo = length_geo / math.sqrt(area_geo) if area_geo > 0 else 0.0
    if slender_geo < min_slenderness:
        raise FeaError(
            "细长比 %.2f < %.1f（L=%.1f, √A=%.1f）：一维杆公式不适用——"
            "端部全约束的影响（圣维南衰减长度 ~√A）会覆盖整个件。"
            "换更细长的零件，或改用板/接触模型"
            % (slender_geo, min_slenderness, length_geo, math.sqrt(area_geo)))

    pm = part_mesh(part, mesh_size=mesh_size, order=order,
                   workdir=workdir, max_volume_error=max_volume_error)
    mesh = pm.mesh
    lo, hi, length = _axis_data(mesh, axis)
    idx = {"x": 0, "y": 1, "z": 2}[axis]
    tol_len = max(length * 1e-6, 1e-9)
    vec = [0.0, 0.0, 0.0]
    vec[idx] = float(force)

    out = solve_face_loaded(
        mesh, fixed_pred=lambda p: p[idx] <= lo + tol_len,
        load_pred=lambda p: p[idx] >= hi - tol_len,
        total_vec=(vec[0], vec[1], vec[2]), workdir=pm.step_path.rsplit(".", 1)[0] + "_axial",
        job="axial_part", E=E, nu=nu)
    if out["stage"] != "solved":
        out["part"] = pm.summary()
        return out

    area_eff = pm.mesh_volume / length
    slenderness = length / math.sqrt(area_eff) if area_eff > 0 else 0.0
    if slenderness < min_slenderness:
        raise FeaError(
            "细长比 %.2f < %.1f：一维杆公式不适用（端部约束会主导整个件）。"
            "要么换更细长的零件，要么改用板/接触模型"
            % (slenderness, min_slenderness))

    disp = out["displacements"]                                # type: ignore[assignment]
    measured = max(abs(v[idx]) for v in disp.values())
    expected = abs(force) * length / (E * area_eff)
    rel = abs(measured - expected) / expected if expected else float("inf")
    out.update({"ok": rel <= tol, "stage": "done", "measured": measured,
                "expected": expected, "relative_error": rel, "tol": tol,
                "axis": axis, "length": length, "area_effective": area_eff,
                "slenderness": slenderness, "part": pm.summary(),
                "stress_nominal": abs(force) / area_eff if area_eff > 0 else float("inf")})
    return out


def cantilever_part(part: brep.Part, *, force: float, E: float, nu: float,
                    mesh_size: float, axis: str = "x", load_axis: str = "z",
                    order: int = 2, tol: float = 5e-2,
                    max_volume_error: float = 0.05,
                    workdir: Optional[str] = None) -> Dict[str, object]:
    """零件当悬臂梁：`axis` 方向的一端全约束，另一端端面受横向力 `load_axis`。

    期望值 δ = PL³/(3EI)，I = b·h³/12，b/h 取另两个方向的包围盒尺寸。

    容差默认 5e-2 而不是 3e-2，原因是**物理而不是离散**：梁理论假设自由
    反平面曲率，而宽板（宽/厚 ≥ 10）受 anticlastic 约束会偏刚，上限是
    1/(1−ν²)（ν=0.3 时约 9%）。实测 200×100×8 板在 h=4/2.67/2 下误差
    3.707%/3.629%/3.608%——加密不变，说明这就是板效应而非网格误差。
    """
    if load_axis == axis:
        raise FeaError("载荷方向不能与梁轴相同")
    ext_geo = _part_extents(part)
    slender_geo = ext_geo[axis] / ext_geo[load_axis] if ext_geo[load_axis] > 0 else 0.0
    if slender_geo < 5.0:
        raise FeaError(
            "长厚比 %.2f < 5.0（L=%.1f, 厚度=%.1f）：梁理论不适用——"
            "剪切变形与端部效应会主导。加长零件，或改用板理论做局部校核"
            % (slender_geo, ext_geo[axis], ext_geo[load_axis]))

    pm = part_mesh(part, mesh_size=mesh_size, order=order,
                   workdir=workdir, max_volume_error=max_volume_error)
    mesh = pm.mesh
    lo, hi, length = _axis_data(mesh, axis)
    ai = {"x": 0, "y": 1, "z": 2}[axis]
    li = {"x": 0, "y": 1, "z": 2}[load_axis]
    tol_len = max(length * 1e-6, 1e-9)
    vec = [0.0, 0.0, 0.0]
    vec[li] = -abs(force)

    out = solve_face_loaded(
        mesh, fixed_pred=lambda p: p[ai] <= lo + tol_len,
        load_pred=lambda p: p[ai] >= hi - tol_len,
        total_vec=(vec[0], vec[1], vec[2]),
        workdir=pm.step_path.rsplit(".", 1)[0] + "_cant", job="cantilever_part",
        E=E, nu=nu)
    if out["stage"] != "solved":
        out["part"] = pm.summary()
        return out

    bbox = mesh.bbox()
    span = {"x": ("ylen", "zlen"), "y": ("xlen", "zlen"), "z": ("xlen", "ylen")}[axis]
    def extent(key: str) -> float:
        return bbox["xmax"] - bbox["xmin"] if key == "xlen" else (
            bbox["ymax"] - bbox["ymin"] if key == "ylen" else bbox["zmax"] - bbox["zmin"])
    # 弯曲发生在 load_axis 方向 → 惯性矩取 (垂直于载荷的宽) × (载荷方向的厚)³/12
    depth_key = {"x": "xlen", "y": "ylen", "z": "zlen"}[load_axis]
    width_key = span[0] if span[1] == depth_key else span[1]
    I = extent(width_key) * extent(depth_key) ** 3 / 12.0
    slenderness = length / extent(depth_key) if extent(depth_key) > 0 else 0.0
    if slenderness < 5.0:
        raise FeaError(
            "长厚比 %.2f < 5.0：梁理论不适用（剪切变形与端部效应会主导）。"
            "加长零件，或改用板理论/更细网格做局部校核" % slenderness)

    disp = out["displacements"]                                # type: ignore[assignment]
    measured = max(abs(v[li]) for v in disp.values())
    expected = abs(force) * length ** 3 / (3 * E * I)
    rel = abs(measured - expected) / expected if expected else float("inf")
    out.update({"ok": rel <= tol, "stage": "done", "measured": measured,
                "expected": expected, "relative_error": rel, "tol": tol,
                "axis": axis, "load_axis": load_axis, "length": length,
                "inertia": I, "slenderness": slenderness, "part": pm.summary(),
                "stress_nominal": (abs(force) * length * (extent(depth_key) / 2.0) / I)
                if I > 0 else float("inf")})
    return out


def _segment_areas(mesh: TetMesh, segments) -> list:
    """按 z 分带统计网格体积 → 每段**实测**截面积（把多边化误差单独拎出来）。"""
    bounds = []
    z = 0.0
    for _d, L in segments:
        bounds.append((z, z + float(L)))
        z += float(L)
    vols = [0.0] * len(bounds)
    for tet in mesh.tets:
        zc = sum(mesh.nodes[n][2] for n in tet) / 4.0
        for i, (z0, z1) in enumerate(bounds):
            if z0 - 1e-9 <= zc <= z1 + 1e-9:
                vols[i] += abs(_tet_volume(mesh, tet))
                break
    return [v / (z1 - z0) for v, (z0, z1) in zip(vols, bounds)]


def _tet_volume(mesh: TetMesh, tet) -> float:
    a, b, c, d = (mesh.nodes[n] for n in tet)
    ax, ay, az = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    bx, by, bz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cx, cy, cz = d[0] - a[0], d[1] - a[1], d[2] - a[2]
    return ((ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx)
             + az * (bx * cy - by * cx)) / 6.0)


def stepped_axial(part: brep.Part, *, segments, force: float, E: float, nu: float,
                  mesh_size: float, order: int = 2, tol: float = 6e-2,
                  max_volume_error: float = 0.05,
                  workdir: Optional[str] = None) -> Dict[str, object]:
    """阶梯轴轴向拉伸。参考解 = 串联柔度 δ = F·Σ(Li/(E·Ai))，Ai 用**名义** πd²/4。

    容差 6e-2 是实测定的，来源有两块（都不该算成"算错"）：
    * 圆柱面多边化：网格体积比零件少 0.8%~2.8%，实测位移随之偏大；
    * 台阶处应力奇异：加密收得很慢（h=4/3/2.2 → 名义偏差 5.53/4.80/4.46%）。
    所以这里用**独立于网格**的名义公式当判据（手算可复核），
    另把网格实测分段面积放进 `areas_mesh` 供诊断（它自己会引入过渡带误差，
    实测反而不收敛：2.17/2.59/3.43%，因此不拿它当判据）。
    """
    ref = refs.stepped_axial(segments=[(float(L), float(d)) for d, L in segments],
                             E=E, force=force)
    pm = part_mesh(part, mesh_size=mesh_size, order=order, workdir=workdir,
                   max_volume_error=max_volume_error)
    mesh = pm.mesh
    lo, hi, length = _axis_data(mesh, "z")
    tol_len = max(length * 1e-6, 1e-9)
    out = solve_face_loaded(
        mesh, fixed_pred=lambda p: p[2] <= lo + tol_len,
        load_pred=lambda p: p[2] >= hi - tol_len,
        total_vec=(0.0, 0.0, float(force)),
        workdir=(pm.step_path.rsplit(".", 1)[0] + "_stax"), job="stepped_axial",
        E=E, nu=nu)
    if out["stage"] != "solved":
        out["part"] = pm.summary()
        return out
    disp = out["displacements"]                                # type: ignore[assignment]
    measured = max(abs(v[2]) for v in disp.values())
    # 判据用名义面积（独立、可手算）；网格实测分段面积只作诊断
    areas_mesh = _segment_areas(mesh, [(d, L) for d, L in segments])
    expected = float(ref["deflection"])
    rel = abs(measured - expected) / expected if expected else float("inf")
    area_avg = pm.mesh_volume / length
    out.update({"ok": rel <= tol, "stage": "done", "measured": measured,
                "expected": expected, "relative_error": rel, "tol": tol,
                "expected_mesh_areas": abs(float(force)) * sum(
                    float(L) / (E * a) for (_d, L), a in zip(segments, areas_mesh)),
                "reference": ref, "part": pm.summary(),
                "areas_mesh": areas_mesh, "areas_nominal": ref["areas"],
                "area_effective": area_avg,
                "stress_nominal": abs(force) / min(areas_mesh) if areas_mesh else 0.0})
    return out


def bracket_cantilever(part: brep.Part, *, length: float, root_height: float,
                       tip_height: float, width: float, force: float, E: float,
                       nu: float, mesh_size: float, order: int = 2,
                       tol: float = 5e-2, max_volume_error: float = 0.05,
                       workdir: Optional[str] = None) -> Dict[str, object]:
    """变截面角撑板当悬臂：参考解 = 梁理论数值积分（见 refs.tapered_cantilever）。"""
    ref = refs.tapered_cantilever(length=length, root_height=root_height,
                                  tip_height=tip_height, width=width,
                                  E=E, force=force)
    pm = part_mesh(part, mesh_size=mesh_size, order=order, workdir=workdir,
                   max_volume_error=max_volume_error)
    mesh = pm.mesh
    lo, hi, span = _axis_data(mesh, "x")
    tol_len = max(span * 1e-6, 1e-9)
    out = solve_face_loaded(
        mesh, fixed_pred=lambda p: p[0] <= lo + tol_len,
        load_pred=lambda p: p[0] >= hi - tol_len,
        total_vec=(0.0, 0.0, -abs(float(force))),
        workdir=(pm.step_path.rsplit(".", 1)[0] + "_brk"), job="bracket",
        E=E, nu=nu)
    if out["stage"] != "solved":
        out["part"] = pm.summary()
        return out
    disp = out["displacements"]                                # type: ignore[assignment]
    measured = max(abs(v[2]) for v in disp.values())
    expected = float(ref["deflection"])
    rel = abs(measured - expected) / expected if expected else float("inf")
    I_root = width * root_height ** 3 / 12.0
    out.update({"ok": rel <= tol, "stage": "done", "measured": measured,
                "expected": expected, "relative_error": rel, "tol": tol,
                "reference": ref, "part": pm.summary(),
                "inertia_root": I_root,
                "stress_nominal": abs(force) * length * (root_height / 2.0) / I_root})
    return out


def equilibrium(out: Dict[str, object]) -> Dict[str, object]:
    """反力与外载是否平衡（没有解析解时的通用判据）。"""
    dat = inpmod.parse_dat(str(out["dat"]))
    react = dat.get("reactions") or {}
    if not react:
        raise FeaError("结果里没有反力块（检查 *NODE PRINT, NSET=FIX）")
    block = next(iter(react.values()))
    fx = sum(v[0] for v in block.values())
    fy = sum(v[1] for v in block.values())
    fz = sum(v[2] for v in block.values())
    return {"reaction": (fx, fy, fz), "nodes": len(block)}
