"""DWG 结构读取（第一阶段）：版本 + 段表（`cc.dwg.reader`）。

说明白范围：**不解析实体**。这里做的是 R13+ 文件头与 Section Locator 表——
足够回答"这个 DWG 是什么版本、多大、内部有几段、段边界是否自洽"，
也就是"不启 AutoCAD 也能查图"的结构层面。实体级解析（对象图/位流解码）成本极高，
在 `docs/backlog.yaml` 里单列为后续项，不在这里假装做过。

格式（R13 起）：
    +0x00  6 字节版本串，如 "AC1032"
    +0x06  1 字节维护版本
    +0x07  1 字节 0x00，+0x08 2 字节 0x00，+0x0A 2 字节 image seeker（未用）
    +0x0D  1 字节 0x00（R2004+）
    +0x0E  2 字节 0x00（R2004+）
    +0x15  6 组 Section Locator Record：(1 字节编号, 4 字节段起点, 4 字节段长)
    ...    每记录后跟 2 字节 CRC（本模块只跳过，不校验）
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import Dict, List, Optional

KNOWN_VERSIONS = {
    "AC1012": "R13", "AC1014": "R14", "AC1015": "2000", "AC1018": "2004",
    "AC1021": "2007", "AC1024": "2010", "AC1027": "2013", "AC1032": "2018+",
}

SECTION_NAMES = {0: "header_vars", 1: "classes", 2: "object_map",
                 3: "obj_free_space", 4: "template", 5: "aux_header"}

MIN_SIZE = 0x15 + 6 * 9 + 6 * 2


class DwgError(ValueError):
    """不是 DWG / 文件被截断 / 段表自相矛盾。"""


@dataclass
class SectionRecord:
    number: int
    offset: int
    size: int
    name: str = ""

    def to_dict(self) -> dict:
        return {"number": self.number, "name": self.name,
                "offset": self.offset, "size": self.size}


@dataclass
class DwgHeader:
    version: str
    release: Optional[str]
    maintenance: int
    size: int
    sections: List[SectionRecord]
    problems: List[str]

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return {"version": self.version, "release": self.release,
                "maintenance": self.maintenance, "bytes": self.size,
                "sections": [s.to_dict() for s in self.sections],
                "problems": self.problems, "ok": self.ok}


def read_header(path: str) -> DwgHeader:
    if not os.path.isfile(path):
        raise DwgError("文件不存在：%s" % path)
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        head = fh.read(min(size, 0x100))
    if len(head) < 6:
        raise DwgError("文件太短（%d 字节），不是 DWG" % len(head))
    version = head[:6].decode("latin-1")
    if not version.startswith("AC10"):
        raise DwgError("不是 DWG（版本串为 %r）" % version)
    if version not in KNOWN_VERSIONS:
        problems_note = "未知版本串 %r（按 R13+ 结构尝试解析）" % version
        release = None
    else:
        problems_note = ""
        release = KNOWN_VERSIONS[version]
    if len(head) < MIN_SIZE:
        raise DwgError("文件被截断：段表需要 ≥%d 字节，实际 %d" % (MIN_SIZE, len(head)))

    maintenance = head[0x06]
    sections: List[SectionRecord] = []
    pos = 0x15
    for _ in range(6):
        if pos + 9 > len(head):
            raise DwgError("段表记录越界（偏移 %d）" % pos)
        number = head[pos]
        offset, length = struct.unpack("<II", head[pos + 1:pos + 9])
        sections.append(SectionRecord(number, offset, length,
                                      SECTION_NAMES.get(number, "unknown")))
        pos += 9 + 2                        # 跳过 CRC

    problems: List[str] = []
    if problems_note:
        problems.append(problems_note)

    # 关键：R2004+ 的文件头布局与 R13 假设**不同**（实测 AutoCAD 2025 导出的
    # AC1032 文件按 R13 偏移读出来是垃圾）。宁可明确拒绝解释，也不输出假段表。
    numbers = [s.number for s in sections]
    if any(n not in SECTION_NAMES for n in numbers) or len(set(numbers)) < 5:
        return DwgHeader(version=version, release=release,
                         maintenance=maintenance, size=size, sections=[],
                         problems=["段表无法按 R13 布局解析（该版本头部布局不同）；"
                                   "需要按真实样本反推 R2004+ 的文件头结构"])
    valid = [s for s in sections if s.size > 0]
    for s in valid:
        if s.offset + s.size > size:
            problems.append("段 %s 越界（%d+%d > %d）"
                            % (s.name, s.offset, s.size, size))
        if s.offset < 0x100:
            problems.append("段 %s 起点 %d 落在文件头内" % (s.name, s.offset))
    # 段之间不该重叠
    ordered = sorted(valid, key=lambda s: s.offset)
    for a, b in zip(ordered, ordered[1:]):
        if a.offset + a.size > b.offset:
            problems.append("段 %s 与 %s 重叠" % (a.name, b.name))
    if len(valid) < 3:
        problems.append("有效段只有 %d 个（正常至少 header/classes/object_map）" % len(valid))

    return DwgHeader(version=version, release=release, maintenance=maintenance,
                     size=size, sections=sections, problems=problems)


def summary_text(header: DwgHeader) -> str:
    lines = ["DWG %s（%s）维护版本 %d，%d 字节"
             % (header.version, header.release or "未知发行", header.maintenance,
                header.size)]
    for s in header.sections:
        if s.size == 0:
            continue
        lines.append("  段 %-14s 偏移 %8d  长度 %8d" % (s.name, s.offset, s.size))
    if header.problems:
        lines.append("问题：")
        lines += ["  ! " + p for p in header.problems]
    else:
        lines.append("段表自洽")
    return "\n".join(lines)
