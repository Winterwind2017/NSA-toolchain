r"""tools/audit_upstream.py —— 上游 Solidworks-MCP-Server 的 188 个工具去向审计

用途：把"上游 188 个工具"逐条对齐到本仓库的三种归宿，**不留空白**：

| 归宿 | 含义 |
|---|---|
| 已覆盖 | 本仓库 `registry` 里有同名条目，且 `implemented=True`（有真机判据） |
| 已判死 | 上游实现调用了不存在/已废弃的 API（见 `docs/UNSUPPORTED.md`） |
| 未复核 | 还没验过——这是待办清单，不是"能用" |

只读上游仓库文件，不 import、不执行。输出 Markdown 表 + JSON。

    python tools/audit_upstream.py \
        --upstream D:\bililive\Solidworks-MCP-Server\server.py \
        --out docs/UPSTREAM_AUDIT.md \
        --json D:\bililive\acad_out\SW_ADV\sim\upstream_audit.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

NAME_RE = re.compile(r"name\s*=\s*[\"'](?P<declared>[^\"']+)[\"']")
DEF_RE = re.compile(r"^(?P<indent>\s*)(?:async\s+)?def\s+(?P<func>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
DOC_RE = re.compile(r'^\s*(?:"""|\'\'\')(?P<doc>[^\n]{0,120})')
API_RE = re.compile(r"\.(?P<api>[A-Z][A-Za-z0-9_]*)\s*\(")
API_PREFIX = ("Get", "Insert", "Create", "Add", "Set", "Save", "Export", "Import",
              "Select", "Edit", "Delete", "Show", "Hide", "Auto", "Feature", "View",
              "Sketch", "Rebuild", "Zoom", "Open", "New", "Close", "Load", "Run",
              "Mirror", "Pattern", "Explode")


def parse_tools(path: str) -> list[dict]:
    """按行解析：`@mcp.tool(` 多行装饰器 + `async def`。

    不用大正则——上游装饰器里有 dict 字面量（annotations），跨行且含括号。
    """
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    defs = []
    for i, line in enumerate(lines):
        m = DEF_RE.match(line)
        if not m:
            continue
        # 往上找紧邻的装饰器块（允许中间有空行/参数行）
        j = i - 1
        decorator = []
        while j >= 0 and len(decorator) < 8:
            s = lines[j].strip()
            if s.startswith("@mcp.tool"):
                decorator.append(s)
                break
            if s in ("", ")") or s.startswith(("name=", "annotations=", "description=",
                                               "title=")) or s.endswith((",", "}", ")")):
                decorator.append(s)
                j -= 1
                continue
            break
        if not decorator or m.group("func").startswith("_"):
            continue              # 不是 MCP 工具（私有 helper：_run/_ok/_err 等）
        defs.append({"index": i, "func": m.group("func"), "decorator": " ".join(decorator)})

    tools = []
    for k, d in enumerate(defs):
        start_i = d["index"]
        end_i = defs[k + 1]["index"] if k + 1 < len(defs) else len(lines)
        body = "\n".join(lines[start_i:end_i])
        declared = NAME_RE.search(d["decorator"])
        doc = DOC_RE.search("\n".join(lines[start_i + 1:start_i + 3]))
        apis = sorted({a for a in API_RE.findall(body) if a.startswith(API_PREFIX)})
        tools.append({
            "declared": declared.group("declared") if declared else None,
            "func": d["func"],
            "line": start_i + 1,
            "title": (doc.group("doc").strip() if doc else "")[:100],
            "apis": apis[:8],
        })
    return tools

def dead_apis(unsupported_md: str) -> set[str]:
    """从 UNSUPPORTED.md 里抠出被判死的 API 名（反引号里的标识符）。"""
    text = open(unsupported_md, encoding="utf-8", errors="replace").read()
    names = set()
    for token in re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", text):
        if token[:1].isupper() and len(token) > 6:
            names.add(token)
    return names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream",
                    default=r"D:\bililive\Solidworks-MCP-Server\server.py")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "UPSTREAM_AUDIT.md"))
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    from swkit.registry import REGISTRY

    tools = parse_tools(args.upstream)
    dead = dead_apis(os.path.join(ROOT, "docs", "UNSUPPORTED.md"))

    rows = []
    for t in tools:
        name = t["declared"] or t["func"]
        entry = REGISTRY.get(name)
        hit_dead = sorted(api for api in t["apis"] if api in dead)
        if entry is not None and entry.implemented:
            verdict, why = "已覆盖", "本仓库有实现且有真机判据"
        elif entry is not None and entry.status == "broken":
            verdict, why = "已判死", "本仓库实测不可用：%s" % (entry.evidence or "")[:60]
        elif entry is not None and entry.status == "unstable":
            verdict, why = "已知不稳", "不进自动回归：%s" % (entry.evidence or "")[:60]
        elif entry is not None and entry.status == "unverified":
            verdict, why = "未达可用", "已登记但没打通：%s" % (entry.evidence or "")[:60]
        elif hit_dead:
            verdict, why = "已判死", "调用 %s（不存在/已废弃）" % ", ".join(hit_dead[:2])
        else:
            verdict, why = "未复核", ""
        rows.append({**t, "name": name, "verdict": verdict, "why": why,
                     "registry_status": entry.status if entry else None,
                     "dead_apis": hit_dead})

    counts = Counter(r["verdict"] for r in rows)
    header = [
        "# 上游 188 工具去向审计",
        "",
        "> 由 `tools/audit_upstream.py` 生成，**只读**上游 `server.py`，不执行。",
        "> 目的：让「上游工具去哪了」这件事可查，而不是「看起来整合过了」。",
        "",
        "## 汇总",
        "",
        "| 归宿 | 数量 | 含义 |",
        "|---|---|---|",
        "| 已覆盖 | %d | 本仓库有实现、有真机判据 |" % counts.get("已覆盖", 0),
        "| 已判死 | %d | 上游实现调用了不存在/已废弃 API，或本仓库实测不可用 |"
        % counts.get("已判死", 0),
        "| 已知不稳 | %d | 能跑但会崩/判据不立，不进自动回归 |" % counts.get("已知不稳", 0),
        "| 未达可用 | %d | 已登记但没打通 |" % counts.get("未达可用", 0),
        "| 未复核 | %d | **待办**：还没验证 |" % counts.get("未复核", 0),
        "",
        "上游共解析出 **%d** 个工具。" % len(rows),
        "",
        "## 明细",
        "",
        "| 工具 | 判死 API | 归属 | 说明 | 上游行 |",
        "|---|---|---|---|---|",
    ]
    body = []
    for r in sorted(rows, key=lambda x: (x["verdict"], x["name"] or "")):
        body.append("| `%s` | %s | %s | %s | %d |" % (
            r["name"],
            ", ".join("`%s`" % a for a in r["dead_apis"]) or "—",
            r["verdict"],
            (r["why"] or r["title"] or "").replace("|", "/")[:70],
            r["line"],
        ))
    # 反向：本仓库有、上游没有的能力（这些是 ③④ 新增，不是"覆盖上游"）
    upstream_names = {r["name"] for r in rows}
    additions = sorted((e.name, e.group) for e in REGISTRY.values()
                       if e.implemented and e.name not in upstream_names)
    # 待办分组：按"能力族"归类（比按第二段更可读、更可分批）
    FAMILIES = (
        ("sketch", ("sketch", "line", "circle", "arc", "spline", "ellipse", "polygon",
                    "rectangle", "trim", "extend", "offset", "fillet", "chamfer",
                    "convert", "construction", "text")),
        ("drawing", ("drawing", "view", "dimension", "note", "balloon", "bom", "table",
                     "section", "detail", "broken", "aux", "centerline", "center",
                     "symbol", "finish", "gtol", "datum", "hole", "sheet_format",
                     "title_block", "annotation", "callout")),
        ("surface", ("surface", "knit", "thicken", "planar", "ruled", "radiate",
                     "mid_surf", "sew", "filled", "boundary", "curve", "composite",
                     "extruded", "revolved", "offset_surf", "trim_surf", "extend_surf")),
        ("sheet_metal", ("sheet", "bend", "flange", "unfold", "fold", "miter", "hem",
                         "tab", "relief", "forming", "sketched")),
        ("weldment", ("weld", "member", "gusset")),
        ("mold", ("mold", "core", "cavity", "parting", "tooling", "shut", "split_body",
                  "tooling_split")),
        ("assembly", ("component", "mate", "assembly", "explode", "interference",
                      "suppress", "mirror", "pattern", "fix", "move", "rotate",
                      "replace", "fix_component")),
        ("feature", ("extrude", "extrude_cut", "revolve", "revolve_cut", "sweep",
                     "loft", "shell", "hole", "chamfer_feature", "fillet_feature",
                     "draft", "rib", "wrap", "split", "combine", "scale", "boss",
                     "cut", "pattern_linear", "pattern_circular", "mirror_feature")),
        ("macro_io", ("macro", "vba", "run", "export", "import", "save", "open",
                      "close", "load", "step", "stl", "pdf", "dxf", "iges")),
        ("inspect", ("get", "set", "list", "status", "info", "props", "property",
                     "material", "config", "custom", "rebuild", "zoom", "mass",
                     "measure", "check")),
    )

    def bucket(name: str) -> str:
        tail = name[3:] if name.startswith("sw_") else name
        for family, keys in FAMILIES:
            if any(k in tail for k in keys):
                return family
        return "other"

    pending = [r["name"] for r in rows if r["verdict"] == "未复核"]
    from collections import Counter as _C
    triage = _C(bucket(n) for n in pending)
    extra = [
        "",
        "## 本仓库超出上游的能力（%d 条）" % len(additions),
        "",
        "这些来自第 ③ 类资产（`sw-extra` 的仿真/运动/元数据）与 ④ 的修复层，"
        "上游 `server.py` 里没有对应工具，所以**不算覆盖上游**：",
        "",
        "| 工具 | 分组 |",
        "|---|---|",
    ]
    for name, group in additions:
        extra.append("| `%s` | %s |" % (name, group))
    extra += [
        "",
        "## 未复核的 %d 条怎么分批" % len(pending),
        "",
        "按能力族归类（只统计未复核条目），便于分批验证：",
        "",
        "| 类别 | 待验证数 |",
        "|---|---|",
    ]
    for key, n in triage.most_common():
        extra.append("| `%s` | %d |" % (key, n))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(header + body + extra) + "\n")

    print("解析 %d 个工具；已覆盖 %d / 已判死 %d / 已登记未编码 %d / 未复核 %d"
          % (len(rows), counts.get("已覆盖", 0), counts.get("已判死", 0),
             counts.get("已登记未编码", 0), counts.get("未复核", 0)))
    print("已写：%s" % args.out)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"total": len(rows), "counts": counts, "rows": rows}, fh,
                      ensure_ascii=False, indent=1)
        print("已写：%s" % args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
