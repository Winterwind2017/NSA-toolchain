"""导出判据（JUDGE_SPEC 2.7）。

文件类能力的判据不能只看"函数返回 True"：`SaveAs` 返回真也可能是 0 字节，
PDF 出图最经典的坑是**出一张白纸也返回成功**。所以这里四层都查：

    L0 文件存在 + size>0 + mtime 是这次写的（防"导到旧文件"）
    L1 文件头魔数（DWG `AC10` / DXF 有 HEADER+ENTITIES 段 / PDF `%PDF-`）
    L2 文件读回来的实体（或页数/尺寸）与内存一致
    L3 PDF 页面尺寸≈A3、且解压后有绘图指令（非空白）
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from . import dxfinfo, pdfinfo
from .base import Readback, verdict

# 属性随块引用走，不算"模型空间实体"；DXF 里它们以 ATTRIB/SEQEND 平铺出现
NON_MODEL_FAMILIES = ("ATTRIB", "ATTDEF", "SEQEND")


def file_info(path: str, since: float, min_bytes: int = 1) -> Dict[str, Any]:
    exists = os.path.isfile(path)
    size = os.path.getsize(path) if exists else 0
    mtime = os.path.getmtime(path) if exists else None
    return {
        "path": path,
        "exists": exists,
        "bytes": size,
        "mtime": mtime,
        "fresh": bool(mtime is not None and mtime >= since - 1.0),
        "min_bytes": min_bytes,
    }


def _file_ok(info: Dict[str, Any]) -> bool:
    return bool(info["exists"] and info["bytes"] >= max(1, info["min_bytes"])
                and info["fresh"])


def _model_families(counts: Dict[str, int]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for fam, n in counts.items():
        if fam in NON_MODEL_FAMILIES:
            continue
        out[fam] = out.get(fam, 0) + int(n)
    return out


# ── DWG ─────────────────────────────────────────────────────────────
def judge_dwg(rb: Readback, *, path: str, since: float,
              min_bytes: int = 1) -> Dict[str, Any]:
    info = file_info(path, since, min_bytes)
    head = b""
    if info["exists"]:
        try:
            with open(path, "rb") as fh:
                head = fh.read(6)
        except OSError as exc:                          # noqa: BLE001
            info["read_error"] = str(exc)
    re = rb.reopened
    counts_ok = bool(re is not None and re.counts == rb.memory.counts)
    handles_ok = bool(re is not None and re.handles == rb.memory.handles)
    checks = {
        "file": _file_ok(info),
        "magic": head[:4].decode("latin-1", "replace") == "AC10",
        "counts": counts_ok,
        "handles": handles_ok,
    }
    detail = {
        "file": info,
        "head": head.decode("latin-1", "replace"),
        "counts_memory": rb.memory.counts,
        "counts_reopened": re.counts if re else None,
        "handles_memory": len(rb.memory.handles),
        "handles_reopened": len(re.handles) if re else None,
        "reopened_source": re.source if re else None,
    }
    raw = {"file": info, "memory_entities": len(rb.memory.entities),
           "reopened_entities": len(re.entities) if re else None}
    return verdict(checks, detail, raw)


# ── DXF ─────────────────────────────────────────────────────────────
def judge_dxf(rb: Readback, *, path: str, since: float,
              dxf: Optional[Dict[str, Any]] = None,
              min_bytes: int = 1) -> Dict[str, Any]:
    info = file_info(path, since, min_bytes)
    dxf = dxf or dxfinfo.read(path)
    mem_fam = _model_families(dxfinfo.histogram(rb.memory.counts,
                                                dxfinfo.family_of_activetype))
    dxf_fam = _model_families(dxf.get("families") or {})
    re = rb.dxf_reopened
    checks = {
        "file": _file_ok(info),
        "sections": ("HEADER" in (dxf.get("sections") or [])
                     and "ENTITIES" in (dxf.get("sections") or [])),
        "parsed": bool(dxf.get("ok")),
        "counts": bool(dxf.get("ok")) and dxf_fam == mem_fam,
        "reopen": bool(re is not None and re.counts == rb.memory.counts),
    }
    detail = {
        "file": info,
        "reader": dxf.get("reader"),
        "counts_memory": rb.memory.counts,
        "families_memory": mem_fam,
        "counts_dxf_raw": dxf.get("counts"),
        "families_dxf": dxf_fam,
        "sections": dxf.get("sections"),
        "counts_reimported": re.counts if re else None,
        "limitations": dxf.get("limitations"),
        "why": dxf.get("why"),
    }
    raw = {"dxf": {k: dxf.get(k) for k in ("counts", "families", "reader",
                                           "sections", "ok", "why")}}
    return verdict(checks, detail, raw)


# ── PDF ─────────────────────────────────────────────────────────────
def judge_pdf(rb: Readback, *, path: str, since: float,
              plot: Optional[Dict[str, Any]] = None,
              expect_pages: int = 1) -> Dict[str, Any]:
    plot = plot or {}
    info = file_info(path, since, min_bytes=1)
    pdf = pdfinfo.parse(path) if info["exists"] else {}
    checks = {
        "file": _file_ok(info),
        "header": str(pdf.get("header") or "").startswith("%PDF-"),
        "pages": pdf.get("pages") == expect_pages,
        "size_a3": pdfinfo.size_matches_a3(pdf.get("size_pt")),
        "ink": bool((pdf.get("vector_ops") or 0) + (pdf.get("text_ops") or 0) > 0),
        "plot_ok": bool(plot.get("ok")),
        "env_restored": bool(plot.get("backgroundplot_restored")),
    }
    detail = {
        "file": info,
        "pages": pdf.get("pages"),
        "size_pt": pdf.get("size_pt"),
        "size_mm": ([round(v / 72.0 * 25.4, 1) for v in pdf["size_pt"]]
                    if pdf.get("size_pt") else None),
        "ops": pdf.get("ops"),
        "decoded_bytes": pdf.get("decoded_bytes"),
        "why": pdf.get("why"),
        "device": plot.get("device"),
        "media": plot.get("media"),
        "plot_warnings": plot.get("warnings"),
        "backgroundplot_before": plot.get("backgroundplot_before"),
        "backgroundplot_after_restore": plot.get("backgroundplot_after_restore"),
        "elapsed_s": plot.get("elapsed_s"),
    }
    raw = {"pdf": {k: pdf.get(k) for k in ("header", "pages", "size_pt",
                                           "vector_ops", "text_ops", "ok",
                                           "why")},
           "plot": plot}
    return verdict(checks, detail, raw)
