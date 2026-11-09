"""swkit.meta.props —— 只读属性 / 批量扫描 / DimXpert / Flow 自检

底层：`swkit/_legacy/sw_adv.py`。

分层（**别混着用**）：

| 能力 | 状态 | 依据 |
|---|---|---|
| `props(file)` 单文件自定义属性 + 配置 | **verified** | 实测可读（含中文属性名） |
| `scan(dir)` 一会话批量扫目录 | **verified** | 实测 275 文件一轮扫完，输出 JSON |
| `sim_status()` Simulation 加载项自检 | verified | 加载项存在性检查 |
| `dxp_info(file)` DimXpert 方案/标注数量 | **unverified** | 可读；`autodim=True` 会**改文件并保存**，默认不动 |
| `flow_check()` Flow Simulation 自检/建工程 | **unverified** | 只做到自检与建工程，未跑通求解 |

安全约定：`dxp_info(..., autodim=False)` 默认只读。**不要**在用户真实工程上开 `autodim`。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .._legacy.runner import json_tail, run, tail_lines

__all__ = ["props", "scan", "sim_status", "dxp_info", "flow_check"]


def _wrap(args, timeout: float = 900.0) -> Dict[str, Any]:
    r = run("adv", args, timeout=timeout)
    out: Dict[str, Any] = {
        "ok": bool(r.get("ok")),
        "data": json_tail(r.get("stdout", "")),
        "elapsed_s": r.get("elapsed_s"),
        "raw_tail": tail_lines(r.get("stdout", ""), 20),
    }
    if not r.get("ok"):
        out["error"] = r.get("error") or tail_lines(r.get("stderr", ""), 6)
    return out


def props(file: str) -> Dict[str, Any]:
    """单文件的配置与自定义属性（verified）。"""
    return _wrap(["props", os.path.abspath(file)], timeout=300)


def scan(folder: str, pattern: str = "", out: str = "", verbose: bool = False,
         timeout_s: float = 3600.0) -> Dict[str, Any]:
    """一个会话里批量扫描目录（verified；大目录请给 `out`，否则输出会很长）。"""
    args = ["scan", os.path.abspath(folder)]
    if pattern:
        args += ["--pattern", pattern]
    if out:
        args += ["--out", os.path.abspath(out)]
    if verbose:
        args += ["--verbose"]
    return _wrap(args, timeout=timeout_s)


def sim_status() -> Dict[str, Any]:
    """Simulation 加载项自检（不打开文档）。"""
    return _wrap(["sim", "status"], timeout=240)


def dxp_info(file: str, config: str = "默认", autodim: bool = False) -> Dict[str, Any]:
    """DimXpert 方案与标注数量。`autodim=True` 会**运行自动尺寸方案并保存文件**，慎用。"""
    args = ["dxp", "info", os.path.abspath(file), "--config", config]
    if autodim:
        args += ["--autodim"]
    res = _wrap(args, timeout=900)
    res["status"] = "unverified"
    res["destructive"] = bool(autodim)
    return res


def flow_check(action: str = "status", file: str = "") -> Dict[str, Any]:
    """Flow Simulation 自检 / 建工程（unverified）。"""
    if action not in ("status", "project"):
        return {"ok": False, "status": "unverified",
                "error": "action 只能是 status 或 project"}
    args = ["flow", action]
    if file:
        args += ["--file", os.path.abspath(file)]
    res = _wrap(args, timeout=900)
    res["status"] = "unverified"
    return res
