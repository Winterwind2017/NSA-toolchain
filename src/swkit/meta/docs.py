"""swkit.meta.docs —— 私有 DocumentMgr（文件库索引 / 属性 / BOM / 图纸表格）

底层：`swkit/_legacy/swdm_lite.py` + SQLite 缓存（默认 `~/.swkit/swdm_lite.db`，
可用 `SWKIT_DM_DB` 覆盖）。

**为什么值得有**：SolidWorks 自带的 DocumentMgr 是收费组件，而 `.sldprt` 载荷是
专有压缩/混淆的（实测：OLE 不是、已知属性名/值原始字节 0 命中、zlib 假阳性、可读 ASCII
只有 73 段噪声）——**没有码本就解不开**。所以这里的正确做法是**让 SolidWorks 自己读**，
再把结果索引进 SQLite。

当前索引实测（2026-10-20 复核）：

* 文件 **275**（`.sldprt` 168 / `.slddrw` 79 / `.sldasm` 28），全部读取成功
* 自定义属性条目 **136**、组件行 **2684**（来自 28 个装配）、工程图视图行 **351**、表格 5（来自 5 张图）

⚠️ 已知限制：`query` **没有全文检索**，只能按 `属性名` 或 `属性名=值`、目录、扩展名过滤
（上游 `sw_extra_mcp.swdm_query(text=...)` 传 `--text` 会因参数不存在而报错——本适配层已修正）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .._legacy.runner import json_tail, run, tail_lines

__all__ = ["stats", "query", "bom", "tables", "show", "sync", "export_csv"]


def _wrap(args: List[str], timeout: float = 600.0) -> Dict[str, Any]:
    r = run("dm", args, timeout=timeout)
    out: Dict[str, Any] = {
        "ok": bool(r.get("ok")),
        "data": json_tail(r.get("stdout", "")),
        "elapsed_s": r.get("elapsed_s"),
        "raw_tail": tail_lines(r.get("stdout", ""), 20),
    }
    if not r.get("ok"):
        out["error"] = r.get("error") or tail_lines(r.get("stderr", ""), 6)
    return out


def stats() -> Dict[str, Any]:
    """索引统计（文件数 / 属性条目 / 组件行 / 视图行 / 表格数）。

    底层打印的是"人读"文本，这里顺手解析成结构体，方便 agent 直接用。
    """
    res = _wrap(["stats"], timeout=180)
    text = res.get("raw_tail") or ""
    parsed: Dict[str, int] = {}
    import re
    patterns = (
        ("files", r"文件数\s*=\s*(\d+)"),
        ("sldprt", r"\.sldprt\s+(\d+)"),
        ("slddrw", r"\.slddrw\s+(\d+)"),
        ("sldasm", r"\.sldasm\s+(\d+)"),
        ("properties", r"属性条目\s*=\s*(\d+)"),
        ("component_rows", r"组件行\s*=\s*(\d+)"),
        ("view_rows", r"工程图视图行\s*=\s*(\d+)"),
        ("tables", r"表格\s*=\s*(\d+)"),
    )
    for key, pat in patterns:
        m = re.search(pat, text)
        if m:
            parsed[key] = int(m.group(1))
    res["data"] = parsed or None
    return res


def query(prop: str = "", folder: str = "", ext: str = "", limit: int = 0,
          csv_path: str = "") -> Dict[str, Any]:
    """按属性/目录/扩展名过滤。

    `prop` 形式：`外形尺寸`（只要求存在该属性）或 `外形尺寸=38x31.3x30`（要求值相等）。
    **不支持自由文本搜索**——见模块文档。
    """
    args = ["query"]
    if prop:
        args += ["--prop", prop]
    if folder:
        args += ["--dir", os.path.abspath(folder)]
    if ext:
        args += ["--ext", ext]
    if limit:
        args += ["--limit", str(int(limit))]
    if csv_path:
        args += ["--csv", os.path.abspath(csv_path)]
    return _wrap(args, timeout=300)


def bom(file: str, as_json: bool = True, limit: int = 200) -> Dict[str, Any]:
    """某装配的 BOM（组件行）。"""
    args = ["bom", os.path.abspath(file), "--limit", str(int(limit))]
    if as_json:
        args += ["--json"]
    return _wrap(args, timeout=300)


def tables(file: str, limit: int = 5, rows: int = 8) -> Dict[str, Any]:
    """某工程图的表格内容。"""
    return _wrap(["tables", os.path.abspath(file), "--limit", str(int(limit)),
                  "--rows", str(int(rows))], timeout=300)


def show(file: str) -> Dict[str, Any]:
    """看单个文件的索引详情。"""
    return _wrap(["show", os.path.abspath(file)], timeout=300)


def sync(folder: str, refresh: bool = False) -> Dict[str, Any]:
    """扫描目录并更新索引（`refresh=True` 忽略缓存全量重读；很慢）。"""
    args = ["sync", os.path.abspath(folder)]
    if refresh:
        args += ["--refresh"]
    return _wrap(args, timeout=3600)


def export_csv(csv_path: str) -> Dict[str, Any]:
    return _wrap(["export", os.path.abspath(csv_path)], timeout=600)
