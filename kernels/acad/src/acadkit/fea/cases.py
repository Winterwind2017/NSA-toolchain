"""三种标准工况：悬臂梁弯曲、圆轴扭转、四边简支板弯曲。

每一种都配一个**闭式解**，测试与 CLI 拿它当场判据：

| 工况 | 解析式 | 系数来源 |
|---|---|---|
| 悬臂梁（端部集中力） | δ = PL³/(3EI)，I = b·h³/12 | Euler-Bernoulli 梁 |
| 圆轴扭转 | θ = TL/(GJ)，G = E/(2(1+ν))，J = πr⁴/2 | Saint-Venant 扭转 |
| 四边简支方板（均布q） | w = α·q·a⁴/D，D = E·t³/(12(1−ν²))，α≈0.00406 | Timoshenko 板理论（ν=0.3） |

**默认用二阶四面体（C3D10）**：线性四面体在弯曲/扭转上偏刚得厉害（实测悬臂
16%、扭转 21%、板 35%），二阶把误差压到 0.01%~0.3%（悬臂/扭转）与 ~3.9%（板）。

容差按**实测**定，不拍脑袋：
* 悬臂梁（order=2，h=5/8）：0.008% / 0.079% → 默认 1e-2；
* 圆轴扭转（order=2，h=5/8）：0.170% / 0.319% → 默认 1e-2；
* 四边简支板（order=2，h=2/3）：3.87% / 3.62% → 默认 5e-2；
  残余偏差来自"边缘所有节点约束 Z"与理想简支的差别，加密不再明显下降。
"""

from __future__ import annotations

import math
import os
from typing import Callable, Dict, List, Optional, Tuple

from . import inp as inpmod
from .mesh import FeaError, TetMesh, Vec3, box_mesh, cylinder_mesh
from .runner import consistent_nodal_loads, run

Vec3T = Tuple[float, float, float]


# ── 通用：指定面固定 + 指定面加载 ──────────────────────────────────
def solve_face_loaded(mesh: TetMesh, *, fixed_pred: Callable[[Vec3], bool],
                      load_pred: Callable[[Vec3], bool], total_vec: Vec3T,
                      workdir: str, job: str, E: float, nu: float,
                      nodal_loads: Optional[Dict[int, Vec3T]] = None,
                      tol_geom: Optional[float] = None,
                      ccx: Optional[str] = None) -> Dict[str, object]:
    """固定面按 pred 选、载荷按 pred 面的一致载荷（或显式 nodal_loads）。"""
    fixed = mesh.select(fixed_pred)
    if not fixed:
        raise FeaError("固定面没选到节点（检查 pred 与容差）")
    if nodal_loads is None:
        loads = consistent_nodal_loads(mesh, load_pred, total_vec)
    else:
        loads = nodal_loads
    if not loads:
        raise FeaError("加载面没选到节点")

    os.makedirs(workdir, exist_ok=True)
    inp_path = os.path.join(workdir, "%s.inp" % job)
    measure = mesh.select(load_pred)
    info = inpmod.write_inp(inp_path, mesh, material=inpmod.Material(E=E, nu=nu),
                            fixed_nodes=fixed, load_nodes=sorted(loads),
                            load_vector=total_vec, nodal_loads=loads,
                            measure_nodes=measure,
                            heading="acadkit fea %s" % job)
    runres = run(inp_path, ccx=ccx)
    if not runres.ok:
        return {"stage": "solve", "mesh": mesh.summary(), "inp": info,
                "run": runres.to_dict(), "ok": False}
    dat = inpmod.parse_dat(runres.files["dat"])
    blocks = dat["displacements"]
    disp = blocks.get("MEASURE") or blocks.get("LOAD") or {}
    return {"stage": "solved", "mesh": mesh.summary(), "inp": info,
            "run": runres.to_dict(), "dat": runres.files["dat"],
            "displacements": disp, "volume": mesh.volume(),
            "fixed": len(fixed), "loaded": len(loads)}


def _verdict(out: Dict[str, object], measured: float, expected: float,
             tol: float, **extra: object) -> Dict[str, object]:
    rel = abs(abs(measured) - abs(expected)) / abs(expected) if expected else float("inf")
    out.update({"measured": measured, "expected": expected,
                "relative_error": rel, "tol": tol, "ok": rel <= tol, "stage": "done"})
    out.update(extra)
    return out


# ── ① 悬臂梁：端部集中力 ────────────────────────────────────────────
def cantilever_beam(*, length: float, width: float, height: float, mesh_size: float,
                    E: float, nu: float, force: float, workdir: str,
                    load_axis: str = "z", tol: float = 1e-2, order: int = 2,
                    ccx: Optional[str] = None) -> Dict[str, object]:
    """沿 X 的悬臂梁，X=0 固定，X=L 端面受集中力（默认 -Z 向下）。

    δ = PL³/(3EI)，I = width·height³/12（力沿 Z 时绕 Y 弯曲）。
    """
    if load_axis not in ("y", "z"):
        raise FeaError("悬臂梁载荷只支持 y 或 z")
    mesh = box_mesh(length, width, height, mesh_size=mesh_size, name="cantilever",
                    order=order)
    axis_idx = {"x": 0, "y": 1, "z": 2}[load_axis]
    vec: List[float] = [0.0, 0.0, 0.0]
    vec[axis_idx] = -abs(force)
    tol_x = max(length * 1e-6, 1e-9)
    out = solve_face_loaded(
        mesh, fixed_pred=lambda p: p[0] <= tol_x,
        load_pred=lambda p: p[0] >= length - tol_x,
        total_vec=(vec[0], vec[1], vec[2]), workdir=workdir, job="cantilever",
        E=E, nu=nu, ccx=ccx)
    if out["stage"] != "solved":
        return out

    disp = out["displacements"]                       # type: ignore[assignment]
    peak = max((abs(v[axis_idx]) for v in disp.values()), default=0.0)
    # 截面惯性矩：力沿 Z 弯曲绕 Y 轴 → I = b·h³/12（b=width, h=height）
    I = (width * height ** 3 / 12.0) if load_axis == "z" else (height * width ** 3 / 12.0)
    expected = abs(force) * length ** 3 / (3 * E * I)
    return _verdict(out, peak, expected, tol,
                    inertia=I, slenderness=length / (height if load_axis == "z" else width))


# ── ② 圆轴扭转 ──────────────────────────────────────────────────────
def consistent_torque_loads(mesh: TetMesh, pred: Callable[[Vec3], bool],
                            torque: float, radius: float) -> Dict[int, Vec3T]:
    """把端面扭矩化成**一致切向载荷**（按表面三角形面积三等分）。

    端面剪应力沿半径线性：τ(r) = T·r/J（实心圆 J=πr⁴/2），方向为切向。
    逐三角形取形心处的 τ 与切向，乘以三角形面积后三等分到节点，
    最后整体缩放使总扭矩精确等于 T（消掉三角化带来的 J 误差）。

    为什么不能"节点力 ∝ r"：那是集中近似，端面三角化不规则时
    会产生局部畸变，实测误差在 13%~52% 之间乱跳、不收敛。
    """
    tris = mesh.surface_triangles(pred)
    if not tris:
        raise FeaError("扭矩面没选到表面三角形")
    J = math.pi * radius ** 4 / 2.0
    acc: Dict[int, List[float]] = {}
    for tri in tris:
        a, b, c = (mesh.nodes[n] for n in tri)
        cx, cy = (a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0
        r = math.hypot(cx, cy)
        if r <= 0:
            continue
        area = mesh.tri_area(tri)
        mag = torque * r / J * area                  # 该三角形上的合力大小
        fx, fy = -cy / r * mag, cx / r * mag
        for n in tri:
            v = acc.setdefault(n, [0.0, 0.0, 0.0])
            v[0] += fx / 3.0
            v[1] += fy / 3.0
    if not acc:
        raise FeaError("扭矩面节点都在轴上")
    # 归一化：让 Σ f_i × r_i 的 Z 分量精确等于 T
    moment = sum(acc[n][1] * mesh.nodes[n][0] - acc[n][0] * mesh.nodes[n][1] for n in acc)
    if abs(moment) < 1e-12:
        raise FeaError("扭矩合力矩为 0，无法归一化")
    scale = torque / moment
    return {n: (v[0] * scale, v[1] * scale, v[2] * scale) for n, v in acc.items()}


def _twist_angle(disp: Dict[int, Vec3T], nodes: Dict[int, Vec3T],
                 axis_idx: int = 2) -> float:
    """最小二乘求扭转角：u ≈ θ·(ẑ × x) 对端面节点拟合。

    用最小二乘而不是取单个节点：单点受网格畸变影响大，拟合对噪声不敏感。
    """
    num = den = 0.0
    for nid, u in disp.items():
        p = nodes.get(nid)
        if p is None:
            continue
        # ẑ × (x,y,z) = (-y, x, 0)
        tx, ty = -p[1], p[0]
        num += u[0] * tx + u[1] * ty
        den += tx * tx + ty * ty
    if den <= 0:
        raise FeaError("端面节点都在轴上，无法拟合扭转角")
    return num / den


def shaft_torsion(*, radius: float, length: float, mesh_size: float,
                  E: float, nu: float, torque: float, workdir: str,
                  tol: float = 1e-2, order: int = 2,
                  ccx: Optional[str] = None) -> Dict[str, object]:
    """沿 Z 的实心圆轴，Z=0 固定端，Z=L 施加扭矩 T（N·mm）。

    θ = TL/(GJ)，G = E/(2(1+ν))，J = πr⁴/2。
    扭矩的做法：端面节点切向力 f_i = T·r_i / Σ r_j²（保证 Σ f_i·r_i = T）。
    """
    mesh = cylinder_mesh(radius, length, mesh_size=mesh_size, axis="z", name="shaft",
                         order=order)
    tol_z = max(length * 1e-6, 1e-9)
    loads = consistent_torque_loads(mesh, lambda p: p[2] >= length - tol_z,
                                   torque, radius)
    total = sum(math.hypot(*v) for v in loads.values())
    out = solve_face_loaded(
        mesh, fixed_pred=lambda p: p[2] <= tol_z,
        load_pred=lambda p: p[2] >= length - tol_z,
        total_vec=(0.0, 0.0, 0.0), workdir=workdir, job="shaft",
        E=E, nu=nu, nodal_loads=loads, ccx=ccx)
    if out["stage"] != "solved":
        return out

    theta = _twist_angle(out["displacements"], mesh.nodes)     # type: ignore[arg-type]
    G = E / (2 * (1 + nu))
    J = math.pi * radius ** 4 / 2.0
    expected = torque * length / (G * J)
    return _verdict(out, theta, expected, tol, shear_modulus=G, polar_J=J,
                    load_resultant=total)


# ── ③ 四边简支方板：均布压力 ────────────────────────────────────────
PLATE_ALPHA = 0.00406          # 四边简支方板中心挠度系数（ν=0.3，Timoshenko）


def simply_supported_plate(*, side: float, thickness: float, mesh_size: float,
                           E: float, nu: float, pressure: float, workdir: str,
                           tol: float = 5e-2, order: int = 2,
                           ccx: Optional[str] = None) -> Dict[str, object]:
    """四边简支方板，板面法向均布压力 q（MPa），求中心挠度。

    w = α·q·a⁴/D，D = E·t³/(12(1−ν²))，α=0.00406（ν=0.3）。
    "简支"用四边节点约束 Z 实现（允许转动）——对实体四面体是常见近似。
    """
    if side <= 0 or thickness <= 0:
        raise FeaError("板边长/厚度必须为正")
    need = 1.2 if order == 2 else 2.0
    if thickness / mesh_size < need:
        raise FeaError("厚度方向至少要有 2 层单元（mesh_size ≤ t/2），当前 t/h=%.2f"
                       % (thickness / mesh_size))
    mesh = box_mesh(side, side, thickness, mesh_size=mesh_size, name="plate", order=order)
    tol_s = max(side * 1e-6, 1e-9)
    tol_t = max(thickness * 1e-6, 1e-9)

    def on_edge(p: Vec3) -> bool:
        x, y, _z = p
        near_x = x <= tol_s or x >= side - tol_s
        near_y = y <= tol_s or y >= side - tol_s
        return near_x or near_y

    fixed = [n for n, p in mesh.nodes.items() if on_edge(p)]
    if len(fixed) < 8:
        raise FeaError("边缘节点太少（%d）" % len(fixed))

    # 均布压力作用在顶面，方向 -Z，总力 = q·a²
    total_force = pressure * side * side
    loads = consistent_nodal_loads(mesh, lambda p: p[2] >= thickness - tol_t,
                                   (0.0, 0.0, -total_force))
    # 约束只加 Z 分量：写 inp 时给 BOUNDARY 三向，这里用"只约束 Z"的等价做法——
    # 把边缘节点的 X/Y 释放不了，所以改为：约束 Z 用单独 nset。
    out = _plate_run(mesh, edge_nodes=fixed, loads=loads, workdir=workdir,
                     E=E, nu=nu, thickness=thickness, ccx=ccx)
    if out["stage"] != "solved":
        return out

    disp = out["displacements"]                       # type: ignore[assignment]
    # 中心挠度：取离板心最近的顶面节点
    cx, cy = side / 2.0, side / 2.0
    cand = [(n, p) for n, p in mesh.nodes.items() if p[2] >= thickness - tol_t]
    nid = min(cand, key=lambda kv: (kv[1][0] - cx) ** 2 + (kv[1][1] - cy) ** 2)[0]
    measured = disp.get(nid, (0.0, 0.0, 0.0))[2]
    D = E * thickness ** 3 / (12 * (1 - nu * nu))
    expected = PLATE_ALPHA * pressure * side ** 4 / D
    return _verdict(out, measured, -expected, tol,
                    flexural_rigidity=D, centre_node=nid)


def _plate_run(mesh: TetMesh, *, edge_nodes: List[int],
               loads: Dict[int, Vec3T], workdir: str, E: float, nu: float,
               thickness: float = 0.0,
               ccx: Optional[str] = None) -> Dict[str, object]:
    """简支板专用：只约束 Z（BOUNDARY 用 3,3），区别于通用 solve_face_loaded。"""
    os.makedirs(workdir, exist_ok=True)
    inp_path = os.path.join(workdir, "plate.inp")
    lines: List[str] = ["*HEADING", "acadkit fea simply supported plate", "*NODE"]
    for nid in sorted(mesh.nodes):
        x, y, z = mesh.nodes[nid]
        lines.append("%d, %.10g, %.10g, %.10g" % (nid, x, y, z))
    lines.append("*ELEMENT, TYPE=%s, ELSET=EALL" % inpmod.ELEMENT_TYPE.get(mesh.order, "C3D4"))
    lines.extend(inpmod._element_lines(mesh))
    lines.append("*NSET, NSET=SUPPORT")
    ids = sorted(set(edge_nodes))
    for k in range(0, len(ids), 16):
        lines.append(", ".join(str(i) for i in ids[k:k + 16]))
    lines.append("*NSET, NSET=LOAD")
    lids = sorted(loads)
    for k in range(0, len(lids), 16):
        lines.append(", ".join(str(i) for i in lids[k:k + 16]))
    # 只约束 Z 会让整个板在 X/Y 上刚体平移（刚度矩阵奇异）；
    # 必须再固定一个角点的 X、Y 平移（转动仍自由）。
    corner = min(mesh.nodes, key=lambda n: mesh.nodes[n][0] ** 2 + mesh.nodes[n][1] ** 2)
    lines.append("*NSET, NSET=ANCHOR")
    lines.append(str(corner))
    lines.append("*BOUNDARY")
    lines.append("SUPPORT, 3, 3")           # 边缘只约束 Z（简支，允许转动）
    lines.append("ANCHOR, 1, 2")            # 角点拴住 X/Y，消除刚体平移
    lines.append("*MATERIAL, NAME=STEEL")
    lines.append("*ELASTIC")
    lines.append("%.10g, %.10g" % (E, nu))
    lines.append("*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL")
    lines.append("*STEP")
    lines.append("*STATIC")
    lines.append("*CLOAD")
    for n in lids:
        fz = loads[n][2]
        if abs(fz) > 0:
            lines.append("%d, 3, %.10g" % (n, fz))
    surf = [n for n, p in mesh.nodes.items() if p[2] >= thickness - thickness * 1e-6]
    lines.append("*NSET, NSET=MEASURE")
    for k in range(0, len(surf), 16):
        lines.append(", ".join(str(i) for i in sorted(surf)[k:k + 16]))
    lines.append("*NODE PRINT, NSET=MEASURE")
    lines.append("U")
    lines.append("*NODE FILE")
    lines.append("U")
    lines.append("*END STEP")
    with open(inp_path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    runres = run(inp_path, ccx=ccx)
    if not runres.ok:
        return {"stage": "solve", "mesh": mesh.summary(), "run": runres.to_dict(),
                "ok": False}
    dat = inpmod.parse_dat(runres.files["dat"])
    blocks = dat["displacements"]
    return {"stage": "solved", "mesh": mesh.summary(), "run": runres.to_dict(),
            "dat": runres.files["dat"],
            "displacements": blocks.get("MEASURE") or blocks.get("LOAD") or {}}
