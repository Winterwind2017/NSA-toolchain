"""P0 抽取：把三处 AutoCAD 自动化的能力清单抽成结构化数据。

来源：
  1. autocad-mcp/server.py  —— 8 个聚合工具 + 各自的 operation 取值
  2. mcp-patches/acad_ext_mcp.py —— TOOLS 键（arc_* 家族）
  3. mcp-patches/acad_mech_build.py —— 顶层函数 + docstring 首行

只读，不执行任何 CAD 操作。
"""

from __future__ import annotations

import ast
import io
import json
import os
import re

OUT = r"D:\bililive\acadkit\docs\_extract.json"
SRV = r"D:\bililive\autocad-mcp\src\autocad_mcp\server.py"
EXT = r"D:\bililive\mcp-patches\acad_ext_mcp.py"
MECH = r"D:\bililive\mcp-patches\acad_mech_build.py"


def read(p: str) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read()


data: dict = {}

# ── 1) autocad-mcp：工具 + operation 字面量
src = read(SRV)
tools = []
for m in re.finditer(r"async def (\w+)\(", src):
    name = m.group(1)
    head = src[max(0, m.start() - 400):m.start()]
    if "@mcp.tool" not in head:
        continue
    block = src[m.end():m.end() + 4000]
    ops = []
    lit = re.search(r"operation:[^=]*=?\s*(?:Literal\[)?([^,\n\)]+)", block)
    if lit:
        ops = re.findall(r"[\"\x27]([a-z0-9_]+)[\"\x27]", lit.group(1))
    if not ops:
        ops = re.findall(r"operation\s*==\s*[\"\x27]([a-z0-9_]+)[\"\x27]", block)
    tools.append({"tool": name, "operations": sorted(set(ops))})
data["autocad_mcp"] = tools

# ── 2) acad_ext_mcp：TOOLS 字典的键
ext = read(EXT)
keys = re.findall(r'^\s{4,8}"([a-z][a-z0-9_]{2,40})"\s*:', ext, re.M)
data["acad_ext_tools"] = sorted(set(keys))

# ── 3) acad_mech_build：函数 + docstring
mech = read(MECH)
data["acad_mech_functions"] = []
try:
    tree = ast.parse(mech)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            doc = (ast.get_docstring(node) or "").splitlines()
            data["acad_mech_functions"].append({
                "name": node.name,
                "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
                "doc": doc[0][:110] if doc else "",
            })
except SyntaxError as exc:
    data["acad_mech_functions"].append({"error": str(exc)})

os.makedirs(os.path.dirname(OUT), exist_ok=True)
io.open(OUT, "w", encoding="utf-8", newline="").write(
    json.dumps(data, ensure_ascii=False, indent=2))

print("autocad-mcp 工具数:", len(tools))
for t in tools:
    print("   %-12s ops=%-2d %s" % (t["tool"], len(t["operations"]),
                                    ", ".join(t["operations"][:10])))
print("acad_ext TOOLS 键:", len(data["acad_ext_tools"]))
print("   " + ", ".join(data["acad_ext_tools"]))
print("acad_mech 函数:", len(data["acad_mech_functions"]))
print("已写:", OUT)
