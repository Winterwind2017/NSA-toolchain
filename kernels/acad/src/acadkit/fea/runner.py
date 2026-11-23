"""调用 CalculiX（ccx）求解，并把"跑完了"和"算对了"分成两件事。

* `find_ccx()` 只在**确认可执行**时返回路径（静态版优先：动态版常缺 MinGW 运行时）；
* `run()` 只负责跑完并收文件，返回退出码与耗时——它**不判断结果对不对**；
* 判断对不对是上层的事：拿位移/反力去和解析式对账（见 tests 与 verify）。
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .mesh import FeaError

# 静态版优先；环境变量可覆盖
CANDIDATES: Sequence[str] = (
    os.environ.get("NSA_CCX", ""),
    r"D:\bililive\tools\calculix\calculix_2.24_4win\ccx_i4_static.exe",
    r"D:\bililive\tools\calculix\calculix_2.24_4win\ccx_i8_static.exe",
    "ccx_i4_static.exe",
    "ccx",
)


@dataclass
class CcxRun:
    ok: bool                 # 只看"进程是否正常结束且产出结果文件"
    exit_code: int
    seconds: float
    job: str
    workdir: str
    files: Dict[str, str]
    stdout_tail: List[str]

    def to_dict(self) -> dict:
        return {"ok": self.ok, "exit_code": self.exit_code,
                "seconds": round(self.seconds, 3), "job": self.job,
                "files": dict(self.files), "stdout_tail": self.stdout_tail[-6:]}


def consistent_nodal_loads(mesh, pred, total_vec) -> Dict[int, Tuple[float, float, float]]:
    """把面上均布载荷化成**一致节点载荷**（按面三角形面积三等分）。

    为什么不能均分到节点数：线性四面体的节点在角上/内部，"均分"不等于
    均布压力的功等效载荷，会引入 O(h) 的假柔度——粗网格上误差可达 1%
    且加密不收敛。按面积分才是有限元该用的。
    """
    tris = mesh.surface_triangles(pred)
    if not tris:
        raise FeaError("载荷面上没有表面三角形（pred 选不到面）")
    total_area = sum(mesh.tri_area(t) for t in tris)
    if total_area <= 0:
        raise FeaError("载荷面面积为 0")
    acc: Dict[int, List[float]] = {}
    for tri in tris:
        share = mesh.tri_area(tri) / total_area / 3.0
        for n in tri:
            v = acc.setdefault(n, [0.0, 0.0, 0.0])
            for i in range(3):
                v[i] += float(total_vec[i]) * share
    return {n: (v[0], v[1], v[2]) for n, v in acc.items()}


def find_ccx() -> Optional[str]:
    for cand in CANDIDATES:
        if not cand:
            continue
        if os.path.isfile(cand):
            return cand
        found = shutil.which(cand)
        if found:
            return found
    return None


def run(inp_path: str, *, ccx: Optional[str] = None, timeout: float = 300.0,
        keep_log: bool = True) -> CcxRun:
    """在 .inp 所在目录跑 ccx（它按 jobname 找 .inp，所以必须在同目录）。"""
    if not os.path.isfile(inp_path):
        raise FeaError("输入文件不存在：%s" % inp_path)
    exe = ccx or find_ccx()
    if not exe:
        raise FeaError("没有找到 ccx 可执行文件（设 NSA_CCX，或装 CalculiX 静态版）")
    workdir = os.path.dirname(os.path.abspath(inp_path))
    job = os.path.splitext(os.path.basename(inp_path))[0]

    # ccx 不接受 -i 带扩展名；也不接受路径分隔符外的修饰
    t0 = time.time()
    try:
        res = subprocess.run([exe, "-i", job], cwd=workdir, capture_output=True,
                             text=True, timeout=timeout, encoding="utf-8",
                             errors="replace")
        code = res.returncode
        out = (res.stdout or "").splitlines()
        err = (res.stderr or "").splitlines()
    except subprocess.TimeoutExpired:
        raise FeaError("ccx 超时（>%.0fs）：%s" % (timeout, job)) from None
    seconds = time.time() - t0

    files: Dict[str, str] = {}
    for ext in ("dat", "frd", "sta", "cvg", "12d"):
        p = os.path.join(workdir, "%s.%s" % (job, ext))
        if os.path.isfile(p):
            files[ext] = p
    ok = code == 0 and "dat" in files and os.path.getsize(files["dat"]) > 0

    if keep_log:
        log = os.path.join(workdir, "%s.ccx.log" % job)
        with open(log, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out + err) + "\n")
        files["log"] = log

    return CcxRun(ok=ok, exit_code=code, seconds=round(seconds, 3), job=job,
                  workdir=workdir, files=files,
                  stdout_tail=out + err)


def _solve_mesh(mesh, *, workdir: str, job: str, E: float, nu: float,
                total_force: float, axial: str = "z",
                ccx: Optional[str] = None) -> Dict[str, object]:
    """画好网格后的通用流程：选面 → 一致载荷 → 写 inp → 跑 ccx → 读位移。"""
    from . import inp as inpmod

    axis = {"x": 0, "y": 1, "z": 2}[axial]
    coords = [mesh.nodes[n][axis] for n in mesh.nodes]
    lo, hi = min(coords), max(coords)
    tol = max((hi - lo) * 1e-6, 1e-9)
    fixed = mesh.select(lambda p: p[axis] <= lo + tol)
    loads = consistent_nodal_loads(mesh, lambda p: p[axis] >= hi - tol,
                                  tuple(total_force if i == axis else 0.0 for i in range(3)))
    if not fixed or not loads:
        raise FeaError("没选到约束面/加载面（改 mesh_size 或检查几何）")

    os.makedirs(workdir, exist_ok=True)
    measure = mesh.select(lambda p: p[axis] >= hi - tol)
    inp_path = os.path.join(workdir, "%s.inp" % job)
    info = inpmod.write_inp(inp_path, mesh, material=inpmod.Material(E=E, nu=nu),
                            fixed_nodes=fixed, load_nodes=sorted(loads),
                            load_vector=tuple(total_force if i == axis else 0.0 for i in range(3)),
                            nodal_loads=loads, measure_nodes=measure,
                            heading="axial %s" % job)
    runres = run(inp_path, ccx=ccx)
    if not runres.ok:
        return {"ok": False, "stage": "solve", "mesh": mesh.summary(),
                "inp": info, "run": runres.to_dict()}
    dat = inpmod.parse_dat(runres.files["dat"])
    blocks = dat["displacements"]
    disp = blocks.get("MEASURE") or blocks.get("LOAD") or {}
    peak = inpmod.max_component(disp, axis=axis)
    length = hi - lo
    volume = mesh.volume()
    return {"ok": None, "stage": "solved", "mesh": mesh.summary(), "mesh_obj": mesh,
            "inp": info,
            "run": runres.to_dict(), "measured": peak["value"],
            "measured_node": peak["node"], "dat": runres.files["dat"],
            "displacements": disp, "len": length, "volume": volume,
            "area_effective": volume / length if length else float("inf")}


def solve_bar(*, length: float, width: float, height: float, mesh_size: float,
              E: float, nu: float, total_force: float, workdir: str,
              tol: float = 1e-6, ccx: Optional[str] = None) -> Dict[str, object]:
    """轴向拉伸算例（含解析期望值），拿来当"链路是否可信"的基准。

    返回 {mesh, inp, run, dat, measured_uz, expected_uz, relative_error, ok}。
    注意 `ok` 的含义是"**与一维杆理论一致**"——这只在 ν=0 时才该成立；
    ν≠0 时固定端会限制横向收缩，位移会偏小（物理正确），不要把 ok=False 当 bug。
    """
    from . import inp as inpmod
    from .mesh import box_mesh

    mesh = box_mesh(width, height, length, mesh_size=mesh_size, name="bar")
    out = _solve_mesh(mesh, workdir=workdir, job="bar", E=E, nu=nu,
                      total_force=total_force, axial="z", ccx=ccx)
    if out["stage"] != "solved":
        return out
    area_geo = width * height
    area_eff = out["area_effective"]              # 用网格自身截面积对账（矩形时应等于 area_geo）
    expected = total_force * length / (E * area_eff)
    rel = abs(abs(out["measured"]) - expected) / expected if expected else float("inf")
    measured = out.pop("measured")
    out.update({"ok": rel <= tol, "stage": "done",
                "measured": measured, "expected": expected,      # 统一键名（CLI 用）
                "measured_uz": measured, "expected_uz": expected,
                "relative_error": rel, "tol": tol,
                "area_geometric": area_geo, "area_effective": area_eff,
                "area_error": abs(area_eff - area_geo) / area_geo})
    return out


def solve_cylinder(*, radius: float, length: float, mesh_size: float,
                   E: float, nu: float, total_force: float, workdir: str,
                   tol: float = 5e-3, ccx: Optional[str] = None) -> Dict[str, object]:
    """圆截面轴向拉伸（沿 Z）。

    容差默认 5e-3 而不是 1e-6：圆柱是非结构化四面体网格，轴向刚度带 O(h²)
    离散误差（实测 h=8/5/3.5/2.5 时 0.139%/0.109%/0.106%/0.027%，单调趋零）；
    再加上网格是内接多面体，有效截面积比 πr² 小约 1.4%——后者已单独报为 area_error。
    """
    from .mesh import cylinder_mesh

    mesh = cylinder_mesh(radius, length, mesh_size=mesh_size, axis="z", name="cyl")
    out = _solve_mesh(mesh, workdir=workdir, job="cyl", E=E, nu=nu,
                      total_force=total_force, axial="z", ccx=ccx)
    if out["stage"] != "solved":
        return out
    area_geo = math.pi * radius * radius
    area_eff = out["area_effective"]              # 圆柱网格是内接多面体，会略小于理想圆面积
    expected = total_force * length / (E * area_eff)
    rel = abs(abs(out["measured"]) - expected) / expected if expected else float("inf")
    measured = out.pop("measured")
    out.update({"ok": rel <= tol, "stage": "done",
                "measured": measured, "expected": expected,      # 统一键名（CLI 用）
                "measured_uz": measured, "expected_uz": expected,
                "relative_error": rel, "tol": tol,
                "area_geometric": area_geo, "area_effective": area_eff,
                "area_error": abs(area_eff - area_geo) / area_geo})
    return out
