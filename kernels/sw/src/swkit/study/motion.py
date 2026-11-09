"""swkit.study.motion —— SolidWorks Motion 适配层

底层：`swkit/_legacy/sw_motion.py`（2026-10-19 实测打通）。

**最关键的一条**：结果集索引是 **4**，不是 1。
`study.GetResults(1)` / `(2)` 是空壳（`IsOutOfDate=True`、值恒为 0）；
`GetResults(4)` 才有数，且必须 `IsOutOfDate == False` 才算有效。
适配层把这个判断留在底层脚本里，返回的 `data` 里应带 `is_out_of_date`。

其它实测结论：

* `GetLinearVelocity / GetLinearAcceleration / GetAngularVelocity` 的组件参数必须是
  **comtypes 强类型 `IComponent2`**，pywin32 的动态对象会失败。
* **位移不要用 `GetCMPosition`** —— 它返回组件自身坐标系，平移时恒定不变。
* 时间轴驱动用 `study.SetTime(t)`（方法），`GetTime` 会随之变化。

典型：

    from swkit.study.motion import read
    res = read(open_path=r"...\\8号机 平移升降搬运组件.SLDASM", samples=11)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .._legacy.runner import json_tail, run, tail_lines

__all__ = ["list_studies", "status", "read"]


def _wrap(args: List[str], timeout: float = 600.0) -> Dict[str, Any]:
    r = run("motion", args, timeout=timeout)
    out: Dict[str, Any] = {
        "ok": bool(r.get("ok")),
        "data": json_tail(r.get("stdout", "")),
        "elapsed_s": r.get("elapsed_s"),
        "raw_tail": tail_lines(r.get("stdout", "")),
    }
    if not r.get("ok"):
        out["error"] = r.get("error") or tail_lines(r.get("stderr", ""), 6)
    return out


def list_studies(open_path: str = "") -> Dict[str, Any]:
    """列算例、马达与结果集可用性。"""
    args = ["list"]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    return _wrap(args, timeout=300)


def status(open_path: str = "") -> Dict[str, Any]:
    args = ["status"]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    return _wrap(args, timeout=300)


def read(open_path: str = "", study: str = "", component: str = "",
         samples: int = 11, out: str = "", csv: str = "") -> Dict[str, Any]:
    """读位移 / 速度 / 加速度随时间的采样。"""
    args = ["read", "--samples", str(int(samples))]
    if study:
        args += ["--study", study]
    if component:
        args += ["--component", component]
    if out:
        args += ["--out", os.path.abspath(out)]
    if csv:
        args += ["--csv", os.path.abspath(csv)]
    if open_path:
        args += ["--open", os.path.abspath(open_path)]
    return _wrap(args, timeout=900)
