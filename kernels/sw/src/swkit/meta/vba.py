"""swkit.meta.vba —— SolidWorks 内嵌 VBA 工程（.swp）的读取/解压/重建

底层：`swkit/_legacy/sw_ovba.py`（OLE 复合文档里的 VBA 目录 + 压缩块解压）。

实测（自带 `enable.swp`）：

* 目录流：压缩 737 B → 解压 **1106 B**；`PROJECTCODEPAGE = 1252`
* 模块 2 个：`ThisLibrary`（MODULETYPE=0x0022）、`EnableOEM`（0x0021）
* `ThisLibrary` 流长 1012 B @ offset 821 → 解出 **304 B 源码**，首行 `Attribute VB_Name = "ThisLibrary"`

用途：
* 审计别人的 `.swp` 里到底写了什么（宏病毒 / 隐藏逻辑排查）
* 把源码写回 `.swp`（`build`），用于**批量生成宏**——SolidWorks 没有"录制宏"的 API，
  程序化造宏只能走这条路。

⚠️ 改 `.swp` 是**破坏性**操作：`build` 会写新文件，务必先备份原文件、且只写到副本上。
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Optional

from .._legacy.runner import json_tail, run, tail_lines

__all__ = ["selftest", "dump", "build"]


def _wrap(args, timeout: float = 300.0) -> Dict[str, Any]:
    r = run("ovba", args, timeout=timeout)
    return {
        "ok": bool(r.get("ok")),
        "data": json_tail(r.get("stdout", "")),
        "elapsed_s": r.get("elapsed_s"),
        "raw_tail": tail_lines(r.get("stdout", ""), 30),
        "error": None if r.get("ok") else (r.get("error") or
                                           tail_lines(r.get("stderr", ""), 6)),
    }


def selftest(swp: str = "") -> Dict[str, Any]:
    """对某个 `.swp` 跑解压/模块列举自检；不给路径则用 SolidWorks 自带的 `enable.swp`。"""
    args = ["selftest"]
    if swp:
        args.append(os.path.abspath(swp))
    return _wrap(args, timeout=300)


def dump(swp: str) -> Dict[str, Any]:
    """导出 `.swp` 里的全部模块源码（打印到 stdout，同时进 `raw_tail`）。"""
    return _wrap(["dump", os.path.abspath(swp)], timeout=300)


def build(template_swp: str, source_text: str, out_path: str,
          module_stream: Optional[str] = None) -> Dict[str, Any]:
    """把 `source_text` 写进 `.swp` 的某个模块流。

    `module_stream=None` 表示让底层自己挑（auto）。**会覆盖 `out_path`**，请指向副本。
    """
    if os.path.abspath(out_path) == os.path.abspath(template_swp):
        return {"ok": False, "error": "拒绝原地覆盖模板：请把 out_path 指到副本"}
    fd, src = tempfile.mkstemp(suffix=".txt", dir=os.path.dirname(os.path.abspath(out_path))
                               or None)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(source_text)
        module = module_stream or "auto"
        return _wrap(["build", os.path.abspath(template_swp), module,
                      src, os.path.abspath(out_path)], timeout=600)
    finally:
        try:
            os.remove(src)
        except OSError:
            pass
