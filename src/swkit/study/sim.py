"""swkit.study.sim —— SolidWorks Simulation（静力）适配层

底层：`swkit/_legacy/sw_sim.py`（8 个命令，2026-10-19 实测打通）。

实测证据（40×40 铝型材角码，52 面，AISI 304）：

* 100 N 静力：位移 min -0.123154 / max **0.698424 mm**
* 1 N 对照：max **0.006984 mm** → 恰好 1/100，**线性静力自洽**
* 安全网格档：`size=0.02 m`、`tol=0.002 m`、`mesh_type=1`（更低会吃满 16 GB）

两个必须知道的限制（否则会误读结果）：

1. **应力读数是会话相关的**：求解后同一会话内读到过 1.497e9；**重新打开文档后恒返回 code 1**。
   本适配层会如实返回 `stress_available=False`，绝不用 0 冒充。
2. 固定端锐边存在**应力奇异**（1497 MPa 远超 AISI 304 屈服 207 MPa）——那是伪值。
   要真应力请在根部加圆角，或取离边缘一定距离的节点。

典型用法：

    from swkit.study.sim import solve
    res = solve(open_path=r"...\\sim_test.SLDPRT", restraint_face=0,
                force_face=1, force_n=100, material="AISI 304")
    res["ok"], res["displacement_mm"]
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .._legacy.runner import json_tail, run, tail_lines

__all__ = ["status", "faces", "list_studies", "setup", "mesh", "run_study",
           "read", "solve", "SAFE_MESH_SIZE", "SAFE_MESH_TOL"]

# 实测安全档：低于这两值会吃满内存（16 GB 峰值）
SAFE_MESH_SIZE = 0.02
SAFE_MESH_TOL = 0.002


def _wrap(key_args: List[str], timeout: float = 900.0) -> Dict[str, Any]:
    r = run("sim", key_args, timeout=timeout)
    data = json_tail(r.get("stdout", ""))
    out: Dict[str, Any] = {
        "ok": bool(r.get("ok")),
        "data": data,
        "elapsed_s": r.get("elapsed_s"),
        "raw_tail": tail_lines(r.get("stdout", "")),
    }
    if not r.get("ok"):
        out["error"] = r.get("error") or tail_lines(r.get("stderr", "") or
                                                    r.get("stdout", ""), 6)
    return out


def status(open_path: str = "") -> Dict[str, Any]:
    """诊断：当前文档、材质、加载项、研究列表。"""
    args = ["status"]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    return _wrap(args, timeout=240)


def faces(open_path: str = "", limit: int = 20) -> Dict[str, Any]:
    """列面（索引 / 中心坐标 mm / 尺寸 mm），用于挑约束面与受力面。"""
    args = ["faces", "--limit", str(int(limit))]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    return _wrap(args, timeout=240)


def list_studies(open_path: str = "") -> Dict[str, Any]:
    args = ["list"]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    return _wrap(args, timeout=240)


def setup(open_path: str = "", restraint_face: int = 0, force_face: int = 1,
          force_n: float = 100.0, material: str = "", mesh: bool = True,
          size: float = SAFE_MESH_SIZE, tol: float = SAFE_MESH_TOL) -> Dict[str, Any]:
    """建静力研究 + 固定约束 + 法向力（可选同时划网格）。"""
    if size < SAFE_MESH_SIZE or tol < SAFE_MESH_TOL:
        return {"ok": False, "error": "网格参数低于实测安全档（size>=%.3f, tol>=%.3f）"
                                      % (SAFE_MESH_SIZE, SAFE_MESH_TOL)}
    args = ["setup", "--restraint-face", str(int(restraint_face)),
            "--force-face", str(int(force_face)), "--force", str(float(force_n))]
    if material:
        args += ["--material", material]
    if not mesh:
        args += ["--no-mesh"]
    args += ["--size", str(float(size)), "--tol", str(float(tol))]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    return _wrap(args, timeout=600)


def mesh(open_path: str = "", study: str = "", size: float = SAFE_MESH_SIZE,
         tol: float = SAFE_MESH_TOL) -> Dict[str, Any]:
    if size < SAFE_MESH_SIZE or tol < SAFE_MESH_TOL:
        return {"ok": False, "error": "网格参数低于实测安全档"}
    args = ["mesh", "--size", str(float(size)), "--tol", str(float(tol))]
    if study:
        args += ["--study", study]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    return _wrap(args, timeout=900)


def run_study(open_path: str = "", study: str = "", timeout_s: int = 3600) -> Dict[str, Any]:
    """求解。40 mm 级零件实测约 11–13 分钟，star.exe 峰值约 15 GB。"""
    args = ["run", "--timeout", str(int(timeout_s))]
    if study:
        args += ["--study", study]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    return _wrap(args, timeout=float(timeout_s) + 120.0)


def read(open_path: str = "", study: str = "", out: str = "") -> Dict[str, Any]:
    """读位移/应力。应力在重开文档后常返回 code 1 —— 这里会如实置 `stress_available=False`。"""
    args = ["read"]
    if study:
        args += ["--study", study]
    if out:
        args += ["--out", os.path.abspath(out)]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    res = _wrap(args, timeout=600)
    data = res.get("data") or {}
    if isinstance(data, dict):
        stress = data.get("stress") or data.get("stress_mpa")
        missing = stress in (None, 0, 0.0) and "code 1" in (res.get("raw_tail") or "")
        res["stress_available"] = not missing
        disp = data.get("displacement") or {}
        if isinstance(disp, dict) and "max" in disp:
            res["displacement_mm"] = disp.get("max")
    return res


def solve(open_path: str = "", restraint_face: int = 0, force_face: int = 1,
          force_n: float = 100.0, material: str = "", out: str = "",
          timeout_s: int = 3600) -> Dict[str, Any]:
    """一条龙：建研究 → 约束 → 力 → 网格 → 求解 → 读结果（约 13–15 分钟）。"""
    args = ["solve", "--restraint-face", str(int(restraint_face)),
            "--force-face", str(int(force_face)), "--force", str(float(force_n)),
            "--timeout", str(int(timeout_s))]
    if material:
        args += ["--material", material]
    if out:
        args += ["--out", os.path.abspath(out)]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    return _wrap(args, timeout=float(timeout_s) + 300.0)
