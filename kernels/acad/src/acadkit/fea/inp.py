"""Abaqus/CalculiX 输入文件写出与结果读取。

只写我们用得到的那一小撮关键字：NODE / ELEMENT(C3D4) / NSET / BOUNDARY /
MATERIAL+ELASTIC / SOLID SECTION / STEP+STATIC / CLOAD / NODE PRINT。
写窄是刻意的——写得越宽，出错面越大，而我们只要"静力 screening"。
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .mesh import FeaError, TetMesh, Vec3


@dataclass
class Material:
    name: str = "STEEL"
    E: float = 210000.0          # MPa
    nu: float = 0.3

    def validate(self) -> "Material":
        E, nu = float(self.E), float(self.nu)
        if not (E > 0) or abs(E) == float("inf"):
            raise FeaError("弹性模量必须为正：%r" % self.E)
        if not (-1.0 < nu < 0.5):
            raise FeaError("泊松比必须在 (-1, 0.5)：%r" % self.nu)
        return self


MAX_PER_LINE = 16      # ccx: "there should not be more than 16 entries in a line"


def _write_id_set(add, name: str, ids: Sequence[int]) -> None:
    ids = sorted(set(int(i) for i in ids))
    for k in range(0, len(ids), MAX_PER_LINE):
        add(", ".join(str(i) for i in ids[k:k + MAX_PER_LINE]))


def write_inp(path: str, mesh: TetMesh, *, material: Material,
              fixed_nodes: Sequence[int], load_nodes: Sequence[int],
              load_vector: Vec3, heading: str = "acadkit fea",
              nodal_loads: Optional[Dict[int, Vec3]] = None,
              print_nodes: bool = True, print_stress: bool = True) -> Dict[str, object]:
    """写 .inp；返回统计（节点数/单元数/载荷合力），便于判据核对。"""
    mat = material.validate()
    if not mesh.tets:
        raise FeaError("网格没有体单元")
    if not fixed_nodes:
        raise FeaError("必须至少约束一个节点，否则刚度矩阵奇异")
    if not load_nodes:
        raise FeaError("必须至少给一个节点加载")
    missing = [n for n in list(fixed_nodes) + list(load_nodes) if n not in mesh.nodes]
    if missing:
        raise FeaError("节点不存在：%s" % missing[:5])

    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        raise FeaError("父目录不存在：%s" % d)

    fx, fy, fz = (float(v) for v in load_vector)
    for v in (fx, fy, fz):
        if v != v or abs(v) == float("inf"):
            raise FeaError("载荷含非有限值：%r" % (load_vector,))
    total = math.sqrt(fx * fx + fy * fy + fz * fz)
    if total <= 0:
        raise FeaError("载荷合力为 0")
    per = (fx / len(load_nodes), fy / len(load_nodes), fz / len(load_nodes))

    lines: List[str] = []
    add = lines.append
    add("*HEADING")
    add(heading)
    add("*NODE")
    for nid in sorted(mesh.nodes):
        x, y, z = mesh.nodes[nid]
        add("%d, %.10g, %.10g, %.10g" % (nid, x, y, z))
    add("*ELEMENT, TYPE=C3D4, ELSET=EALL")
    for i, tet in enumerate(mesh.tets, 1):
        add("%d, %d, %d, %d, %d" % (i, tet[0], tet[1], tet[2], tet[3]))
    add("*NSET, NSET=FIX")
    _write_id_set(add, "FIX", fixed_nodes)
    add("*NSET, NSET=LOAD")
    _write_id_set(add, "LOAD", load_nodes)
    add("*BOUNDARY")
    add("FIX, 1, 3")
    add("*MATERIAL, NAME=%s" % mat.name)
    add("*ELASTIC")
    add("%.10g, %.10g" % (mat.E, mat.nu))
    add("*SOLID SECTION, ELSET=EALL, MATERIAL=%s" % mat.name)
    add("*STEP")
    add("*STATIC")
    add("*CLOAD")
    if nodal_loads:
        for n in sorted(nodal_loads):
            lx, ly, lz = nodal_loads[n]
            if abs(lx) > 0:
                add("%d, 1, %.10g" % (n, lx))
            if abs(ly) > 0:
                add("%d, 2, %.10g" % (n, ly))
            if abs(lz) > 0:
                add("%d, 3, %.10g" % (n, lz))
    else:
        for n in sorted(set(load_nodes)):
            add("%d, 1, %.10g" % (n, per[0]))
            add("%d, 2, %.10g" % (n, per[1]))
            add("%d, 3, %.10g" % (n, per[2]))
    if print_nodes:
        add("*NODE PRINT, NSET=LOAD, TOTALS=YES")
        add("U")
        add("*NODE PRINT, NSET=FIX")
        add("RF")
    add("*NODE FILE")
    add("U")
    if print_stress:
        add("*EL FILE")
        add("S")
    add("*END STEP")

    text = "\n".join(lines) + "\n"
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write(text)
    return {"path": path, "bytes": len(text), "nodes": len(mesh.nodes),
            "elements": len(mesh.tets), "fixed": len(set(fixed_nodes)),
            "loaded": len(set(load_nodes)), "force_total": total,
            "force_total_vec": (fx, fy, fz)}


# ── 结果读取 ────────────────────────────────────────────────────────
_DISP_HEADER = re.compile(r"displacements \(vx,vy,vz\) for set (\S+)", re.I)
_REACTION_HEADER = re.compile(r"forces \(fx,fy,fz\) for set (\S+)", re.I)
_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[EeDd][-+]?\d+)?")


def _to_float(tok: str) -> float:
    return float(tok.replace("D", "E").replace("d", "e"))


def parse_dat(path: str) -> Dict[str, object]:
    """从 .dat 里读位移与反力（按 set 分组）。

    只认 CalculiX 的表格行（首列是节点号，后三列是分量）；别的行一律跳过，
    宁可少读也不误读。
    """
    if not os.path.isfile(path):
        raise FeaError("结果文件不存在：%s" % path)
    blocks: Dict[str, Dict[str, Dict[int, Tuple[float, float, float]]]] = {}
    current: Optional[Tuple[str, str]] = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            m = _DISP_HEADER.search(line)
            if m:
                current = ("displacements", m.group(1))
                blocks.setdefault("displacements", {})[m.group(1)] = {}
                continue
            m = _REACTION_HEADER.search(line)
            if m:
                current = ("reactions", m.group(1))
                blocks.setdefault("reactions", {})[m.group(1)] = {}
                continue
            if current is None:
                continue
            stripped = line.strip()
            if not stripped:
                continue                      # 空行只是分隔，**不能**清掉当前块
            if stripped[0].isalpha() or stripped.startswith("*"):
                current = None
                continue
            toks = stripped.replace(",", " ").split()
            if len(toks) < 4:
                continue
            try:
                nid = int(toks[0])
                vals = tuple(_to_float(t) for t in toks[1:4])
            except ValueError:
                current = None
                continue
            if not all(math.isfinite(v) for v in vals):
                raise FeaError("结果里出现非有限值：%r" % (line,))
            blocks[current[0]][current[1]][nid] = vals          # type: ignore[index]
    if not blocks.get("displacements"):
        raise FeaError("结果里没有位移块（检查 *NODE PRINT 是否被写出）：%s" % path)
    return blocks


def max_component(disp: Dict[int, Tuple[float, float, float]], axis: int = 2) -> Dict[str, object]:
    """某个方向分量的最大绝对值及所在节点。"""
    if not disp:
        raise FeaError("位移为空")
    nid = max(disp, key=lambda k: abs(disp[k][axis]))
    return {"node": nid, "value": disp[nid][axis], "magnitude": abs(disp[nid][axis])}


def sum_reaction(reactions: Dict[int, Tuple[float, float, float]]) -> Tuple[float, float, float]:
    fx = sum(v[0] for v in reactions.values())
    fy = sum(v[1] for v in reactions.values())
    fz = sum(v[2] for v in reactions.values())
    return (fx, fy, fz)
