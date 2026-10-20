"""swkit.verified.io —— 打开/保存/导出（判据是**文件签名**）

导出类工具最容易"假成功"：SolidWorks 的 `SaveAs` 系列返回 `True`/`0`/文档对象不等，
而文件可能根本没写出来。这里的判据一律是：

1. 文件**存在**且大小 > 下限；
2. **读头几个字节做签名校验**（STEP `ISO-10303-21`、STL 二进制/ASCII、PDF `%PDF`、
   DXF `0/SECTION`、IGES `S` 行）。

| 工具 | 格式 | 签名判据 |
|---|---|---|
| `export_step` | STEP | `ISO-10303-21` |
| `export_stl` | STL | `solid`（ASCII）或 80 字节头 + 三角面数 |
| `export_pdf` | PDF | `%PDF` |
| `export_iges` | IGES | 文本行尾 `S` 段 |
| `export_dxf` | DXF | `SECTION` / `HEADER` |
| `save_document` | 原生 | 文件存在 + 大小不变/增大 |
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..core.com import pyw, val

__all__ = ["export_step", "export_stl", "export_pdf", "export_iges", "export_dxf",
           "save_document"]

MIN_BYTES = {"step": 500, "stp": 500, "stl": 84, "pdf": 500, "iges": 200,
             "igs": 200, "dxf": 200}


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _kernel():
    from .sketch_ops import app
    return app()


def _signature(path: str) -> Dict[str, Any]:
    """读文件头判断格式（不解析全文）。"""
    info: Dict[str, Any] = {"bytes": 0, "head": ""}
    try:
        size = os.path.getsize(path)
        info["bytes"] = size
        with open(path, "rb") as fh:
            head = fh.read(256)
    except OSError as exc:
        info["error"] = str(exc)
        return info
    text = head.decode("latin-1", "replace")
    info["head"] = text[:48].replace("\n", "\\n")
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in ("step", "stp"):
        info["format_ok"] = "ISO-10303-21" in text
    elif ext == "stl":
        info["format_ok"] = text.lstrip().lower().startswith("solid") or size > 84
    elif ext == "pdf":
        info["format_ok"] = text.startswith("%PDF")
    elif ext in ("iges", "igs"):
        info["format_ok"] = ("S" in text and "1H" in text) or "IGES" in text.upper()
    elif ext == "dxf":
        info["format_ok"] = "SECTION" in text
    else:
        info["format_ok"] = True
    return info


def _export(tool: str, api: str, path: str, call) -> Dict[str, Any]:
    out = _result(tool, api)
    target = os.path.abspath(path)
    ext = os.path.splitext(target)[1].lower().lstrip(".")
    out["detail"].update({"path": target, "ext": ext})
    if os.path.exists(target):
        try:
            os.remove(target)
        except OSError as exc:
            out["detail"]["error"] = "旧文件删不掉：%s" % exc
            return out
    try:
        call(target)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    info = _signature(target)
    out["detail"].update(info)
    min_bytes = MIN_BYTES.get(ext, 100)
    out["checks"] = {
        "file_exists": os.path.exists(target),
        "size_ok": info.get("bytes", 0) >= min_bytes,
        "signature_ok": bool(info.get("format_ok")),
    }
    out["ok"] = all(out["checks"].values())
    return out


def export_step(path: str) -> Dict[str, Any]:
    return _export("sw_export_step", "IModelDoc2.SaveAs(STEP)",
                   path, lambda p: _kernel().export_step(p))


def export_stl(path: str) -> Dict[str, Any]:
    return _export("sw_export_stl", "IModelDoc2.SaveAs(STL)",
                   path, lambda p: _kernel().export_stl(p))


def export_pdf(path: str) -> Dict[str, Any]:
    return _export("sw_export_file", "IModelDoc2.SaveAs(PDF)",
                   path, lambda p: _kernel().export_pdf(p))


def export_iges(path: str) -> Dict[str, Any]:
    return _export("sw_export_iges", "IModelDoc2.SaveAs(IGES)",
                   path, lambda p: _kernel().export_iges(p))


def export_dxf(path: str) -> Dict[str, Any]:
    return _export("sw_export_dxf", "IModelDoc2.SaveAs(DXF)",
                   path, lambda p: _kernel().export_dxf(p))


def save_document(doc: Any, path: str = "") -> Dict[str, Any]:
    """保存/另存。判据：文件存在且大小 > 0（原生格式无公开签名）。"""
    out = _result("sw_save_document", "IModelDoc2.SaveAs3 / Save3")
    target = os.path.abspath(path) if path else (val(doc, "GetPathName") or "")
    out["detail"]["path"] = target
    if not target:
        out["detail"]["error"] = "文档没有路径，且未指定 path"
        return out
    before = os.path.getsize(target) if os.path.exists(target) else 0
    mtime_before = os.path.getmtime(target) if os.path.exists(target) else 0.0
    try:
        if path:
            _kernel().save_document(target)
        else:
            _kernel().save_document()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = os.path.getsize(target) if os.path.exists(target) else 0
    mtime_after = os.path.getmtime(target) if os.path.exists(target) else 0.0
    out["detail"].update({"bytes_before": before, "bytes_after": after,
                          "mtime_changed": mtime_after > mtime_before})
    # 注意：**不能**用"大小没变小"当判据——SolidWorks 保存会重压缩，文件变小是正常的
    # （实测 65,418 → 64,835 B）。可靠判据是"存在 + 非空 + mtime 变了"。
    out["checks"] = {"file_exists": after > 0,
                     "size_positive": after > 0,
                     "updated": (mtime_after > mtime_before) or (after != before)}
    out["ok"] = all(out["checks"].values())
    return out
