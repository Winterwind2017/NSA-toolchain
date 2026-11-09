"""梯形图正文的**离线读取器**：把 `LadderBlocks.data` 的 `V1:` DSL 解析成结构。

DSL 形态（实测定型）：
    V1:6:1:1:1:1:1:1:a:X:a:X:c:Y:cb{fg=fg{dim=12x1:es=[
        e{s=ce{op=ct{op=#:ct=a:as=[as{vt=Abl}]}:args=[d{s=#:a=0:vt=nn}]}:pos=0,0}
       :e{s=ce{op=cl{op=#:ct=a:as=[as{vt=Abl}]}:args=[d{s=#:a=0:vt=nn}]}:pos=2,0}
    ]:vs=[v{pos=1,1}]}}

  · 前缀 `a:X`/`c:Y`/`b:M` 是出现的软元件种类（顺序即首次使用顺序）
  · `op=ct` 触点、`op=cl` 线圈或应用指令（应用指令多一个 `as{vt=A16}` 和参数）
  · `pos=列,行`
  · `vs=[v{pos=列,行}]` 竖线
  · `d{s=#:a=N:vt=nn}` 里的 N 是**软元件地址**（X0→0、X1→1、Y0→0）
"""

import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

ELEM_RE = re.compile(
    r"e\{s=(?P<body>ce\{.*?\}|-)\:pos=(?P<col>\d+),(?P<row>\d+)\}", re.S)
OP_RE = re.compile(r"op=(?P<op>ct|cl)")
ADDR_RE = re.compile(r"d\{s=\#\:a=(?P<a>\d+)\:vt=")
CONST_RE = re.compile(r"c\{s=\#\:v=(?P<v>-?\d+)")
VS_RE = re.compile(r"v\{pos=(?P<col>\d+),(?P<row>\d+)\}")
DEV_RE = re.compile(r":([a-z]):([A-Z][A-Z0-9_]{0,3})(?=[:{])")
DIM_RE = re.compile(r"dim=(?P<cols>\d+)x(?P<rows>\d+)")
INSTR_RE = re.compile(r":([A-Z][A-Z0-9_]{1,15}):")


def read_blocks(gx3: str | Path) -> list[dict]:
    """读一个 .gx3 里**所有**梯形图正文块（可能多程序，故返回全部 LDDB 的行）。"""
    gx3 = Path(gx3)
    out: list[dict] = []
    if not gx3.exists():
        return out
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(gx3) as z:
            z.extractall(tmp)
        for db in sorted(Path(tmp).rglob("*_LDDB.db")):
            con = sqlite3.connect(str(db))
            try:
                rows = list(con.execute(
                    "select blocktype, pos, data from LadderBlocks order by pos"))
            finally:
                con.close()
            for blocktype, pos, data in rows:
                out.append(_parse_block(db.name, blocktype, pos, data or ""))
    return out


def _parse_block(db_name: str, blocktype: int, pos: float, data: str) -> dict:
    dim = DIM_RE.search(data)
    head = data.split("cb{", 1)[0]
    devices = [m.group(2) for m in DEV_RE.finditer(head)]
    instr = [m.group(1) for m in INSTR_RE.finditer(head)]
    elements = []
    for m in ELEM_RE.finditer(data):
        body = m.group("body")
        col, row = int(m.group("col")), int(m.group("row"))
        if body == "-":
            elements.append({"col": col, "row": row, "op": "", "addr": None,
                             "const": None, "kind": "empty"})
            continue
        op = OP_RE.search(body)
        op = op.group("op") if op else ""
        addr = ADDR_RE.search(body)
        const = CONST_RE.search(body)
        kind = {"ct": "contact", "cl": "coil"}.get(op, op or "?")
        elements.append({"col": col, "row": row, "op": op, "kind": kind,
                         "addr": int(addr.group("a")) if addr else None,
                         "const": int(const.group("v")) if const else None})
    verticals = [{"col": int(m.group("col")), "row": int(m.group("row"))}
                 for m in VS_RE.finditer(data)]
    return {"db": db_name, "blocktype": blocktype, "pos": pos,
            "cols": int(dim.group("cols")) if dim else None,
            "rows": int(dim.group("rows")) if dim else None,
            "devices": devices, "instructions": instr,
            "elements": elements, "verticals": verticals, "raw": data}


def summarize(block: dict) -> str:
    """压成一行人类可读：`X0 -[ ]- X1 -( )- Y0`（地址来自 a=，类型看前缀）。"""
    parts = []
    for e in sorted([x for x in block["elements"] if x["kind"] != "empty"],
                    key=lambda x: (x["row"], x["col"])):
        tag = {"contact": "-[ ]-", "coil": "-( )-"}.get(e["kind"], e["kind"])
        val = "K%d" % e["const"] if e["const"] is not None else ""
        val += "" if e["addr"] is None else "a%d" % e["addr"]
        parts.append("%s%s@%d,%d" % (tag, val, e["col"], e["row"]))
    return " ".join(parts)


def count_kinds(blocks: list[dict]) -> dict:
    out = {"contact": 0, "coil": 0, "empty": 0}
    for b in blocks:
        for e in b["elements"]:
            out[e["kind"]] = out.get(e["kind"], 0) + 1
    return out
