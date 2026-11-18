"""格式探测与"存盘无损"差异报告（对照 CADCraft `crates/io` + `save_reports_not_saved`）。

两件事：
* `sniff(path)`  看文件头判断格式（DWG/DXF/PDF/STEP/IGES/STL…），用于"别把 PDF 当 DXF 读"；
* `diff_documents(a, b)`  按实体签名比对两份 DXF，报告**丢了什么**——
  这是"保存不丢数据"从口号变成可验证判据的那一步。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .document import Document, Entity


class SniffError(ValueError):
    pass


_MAGIC: List[Tuple[bytes, str]] = [
    (b"AutoCAD Binary DXF", "dxf-binary"),
    (b"AC10", "dwg"),
    (b"%PDF", "pdf"),
    (b"ISO-10303-21", "step"),
    (b"solid ", "stl-ascii"),
    (b"ply\n", "ply"),
    (b"\x89PNG", "png"),
    (b"\xff\xd8\xff", "jpeg"),
]


def sniff(path: str) -> dict:
    """返回 {format, header, size}；未知格式 format="unknown"。"""
    if not os.path.isfile(path):
        raise SniffError("文件不存在：%s" % path)
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        head = fh.read(64)
    for magic, name in _MAGIC:
        if head.startswith(magic):
            return {"format": name, "header": head[:16].decode("latin-1", "replace"),
                    "size": size}
    # DXF（ASCII）通常是 "0\nSECTION" 或 "  0\nSECTION"
    text = head[:32].decode("latin-1", "replace").replace("\r", "")
    stripped = text.lstrip()
    if stripped.startswith("0\nSECTION") or stripped.startswith("0\nEOF"):
        return {"format": "dxf", "header": text[:16], "size": size}
    if head[:2] == b"PK":
        return {"format": "zip-like", "header": head[:16].decode("latin-1", "replace"),
                "size": size}
    return {"format": "unknown", "header": head[:16].decode("latin-1", "replace"),
            "size": size}


def _ent_digest(ent: Entity) -> str:
    h = hashlib.sha256()
    for code, value in ent.pairs:
        h.update(("%d|%s\n" % (code, value)).encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def _index(doc: Document) -> Dict[str, Entity]:
    """以句柄索引；无句柄的用"类型#序号"占位（明确标注，不假装有身份）。"""
    out: Dict[str, Entity] = {}
    counters: Dict[str, int] = {}
    for ent in doc.entities():
        if ent.handle:
            key = "h:%s" % ent.handle
        else:
            n = counters.get(ent.type, 0)
            counters[ent.type] = n + 1
            key = "n:%s#%d" % (ent.type, n)
        out[key] = ent
    return out


@dataclass
class DiffReport:
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)

    @property
    def lost(self) -> int:
        """真正要紧的数：原文件有、新文件没有的实体数。"""
        return len(self.removed)

    def to_dict(self) -> dict:
        return {"added": self.added, "removed": self.removed,
                "changed": self.changed, "lost": self.lost}


def diff_documents(old: Document, new: Document) -> DiffReport:
    a, b = _index(old), _index(new)
    rep = DiffReport()
    for key in sorted(set(a) - set(b)):
        rep.removed.append(key)
    for key in sorted(set(b) - set(a)):
        rep.added.append(key)
    for key in sorted(set(a) & set(b)):
        if _ent_digest(a[key]) != _ent_digest(b[key]):
            rep.changed.append(key)
    return rep
