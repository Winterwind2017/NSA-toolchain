#!/usr/bin/env python3
"""生成 `docs/CADCRAFT_MINE.md`：从 CADCraft 能挖多少东西、一共多少工时。

    python tools/gen_cadcraft_mine.py            # 写文件
    python tools/gen_cadcraft_mine.py --check    # 只检查（tests / pre-push）

数据源：`docs/cadcraft_mine.yaml`（人工分析，2026-11-18 对着仓库树逐 crate 过了一遍）。
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "CADCRAFT_MINE.md")
SRC = os.path.join(ROOT, "docs", "cadcraft_mine.yaml")

MODE_LABEL = {
    "port": "移植（改写成 Python）",
    "spec": "测试当规格",
    "design": "读设计做参考",
    "read": "只读了解",
    "never": "不挖",
}
MODE_ORDER = ("port", "spec", "design", "read")

PROSE_HEAD = """# 从 CADCraft 能挖什么（全量清单）

> 本文件由 `python tools/gen_cadcraft_mine.py` 从 `docs/cadcraft_mine.yaml` 生成。**不要手改**。
> 最近更新：%(updated)s

## 口径

上游：%(repo)s（%(license)s，12 crate，engine 133 个源文件 + 110 个测试文件）。

**许可证**：MIT OR Apache-2.0 —— 允许移植/改写/商用，但必须署名。
凡 `移植` 类条目落地时，都要往 `NOTICE.md` / `ATTRIBUTION.md` 加一条。

**这份清单回答的是**：把 CADCraft 的**优势**吸收进 nsa-toolchain，一共有多少东西、多少工时。
它**不是** AutoCAD 能力补全计划（那个在 `docs/BACKLOG.md`）——两者唯一重叠的是
`dxf` 解析与「真实语料/无损存盘」这类**方法**。

## 一个前提判断

CADCraft 的最大资产**不是**它的几何内核（那部分对我们无用，几何由 AutoCAD 提供），
而是三样东西：

1. **纯算法件**：LM 约束求解、曲线偏移/求交、填充边界探测——与 CAD 平台无关，可移植；
2. **行为规格**：110 个测试把 AutoCAD 的边界行为写成了可执行描述——免费的真机判据；
3. **数据模型**：关联标注、动态块夹点、阵列/快速标注的建模方式——AutoCAD 没有公开规格。

"""

PROSE_TAIL = """
## 怎么用这份清单

1. **先看总量**：%(total)gh / %(n)d 项。其中「移植」%(port)d 项 %(port_h)gh，
   「测试当规格」%(spec)d 项 %(spec_h)gh —— 后者性价比最高（不用写实现，直接把测试变判据）。
2. **按价值挑**：价值 5 的两条是 `cc.constraints.solver`（参数驱动重建）与
   `cc.dxf.reader`（读别人的图）+ `cc.spec.robustness`（畸形输入）；
   这三条分别补的是「改图」「承接旧项目」「不静默失败」。
3. **不要整体移植内核**：只挑上面列的算法与规格，几何仍交给 AutoCAD。
4. 移植任何代码前，先把 `ATTRIBUTION.md` 建起来（`cc.attribution` 那 2h 就是干这个的）。

## 明确不挖

| 不挖 | 为什么 |
|---|---|
%(never)s
"""


def _load() -> Dict[str, Any]:
    import yaml

    with open(SRC, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build() -> Dict[str, Any]:
    data = _load()
    items = list(data.get("items") or [])
    areas = {a["key"]: a for a in (data.get("areas") or [])}
    seen = set()
    for it in items:
        if it["id"] in seen:
            raise SystemExit("cadcraft_mine.yaml 里 %s 重复" % it["id"])
        seen.add(it["id"])
        if it.get("area") not in areas:
            raise SystemExit("%s 的 area=%r 未登记" % (it["id"], it.get("area")))
        if it.get("mode") not in MODE_LABEL:
            raise SystemExit("%s 的 mode=%r 非法" % (it["id"], it.get("mode")))
        it["hours"] = float(it.get("hours") or 0)
        it["value"] = int(it.get("value") or 1)
    return {"data": data, "items": items, "areas": areas}


def render() -> str:
    built = build()
    data, items, areas = built["data"], built["items"], built["areas"]
    total = sum(i["hours"] for i in items)
    by_mode: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        by_mode.setdefault(it["mode"], []).append(it)

    lines = [PROSE_HEAD % {
        "updated": data.get("updated_at", "—"),
        "repo": (data.get("upstream") or {}).get("repo", "—"),
        "license": (data.get("upstream") or {}).get("license", "—"),
    }]

    lines += ["## 一、总量", "",
              "| 吸收方式 | 项数 | 工时 | 占比 | 含义 |", "|---|---:|---:|---:|---|"]
    for m in MODE_ORDER:
        group = by_mode.get(m) or []
        if not group:
            continue
        h = sum(i["hours"] for i in group)
        lines.append("| %s | %d | %gh | %.0f%% | %s |"
                     % (MODE_LABEL[m], len(group), h, 100.0 * h / total if total else 0,
                        {
                            "port": "真改写成 Python 进 nsa-toolchain",
                            "spec": "把它的测试翻译成我们的真机判据",
                            "design": "读模型/状态机，指导自己实现",
                            "read": "只为了解，不产出代码",
                        }[m]))
    lines.append("| **合计** | **%d** | **%gh** | 100%% | — |" % (len(items), total))
    lines.append("")

    lines += ["## 二、按域", "",
              "| 域 | 项数 | 工时 | 为什么值得挖 |", "|---|---:|---:|---|"]
    for key, area in areas.items():
        mine = [i for i in items if i["area"] == key]
        lines.append("| %s（`%s`） | %d | %gh | %s |"
                     % (area.get("title", key), key, len(mine),
                        sum(i["hours"] for i in mine), area.get("why", "")))
    lines.append("")

    lines += ["## 三、全量明细", "",
              "排序：价值分降序 → 工时升序。`src` 是对应仓库路径（可直接去看）。", "",
              "| # | 资产 | 能拿什么 | 方式 | 价值 | 工时 | 源路径 | 说明 |",
              "|---|---|---|---|---:|---:|---|---|"]
    ordered = sorted(items, key=lambda i: (-i["value"], i["hours"], i["id"]))
    for n, it in enumerate(ordered, 1):
        lines.append("| %d | `%s` | %s | %s | %d | %gh | %s | %s |"
                     % (n, it["id"], it.get("title", ""),
                        MODE_LABEL.get(it["mode"], it["mode"]), it["value"], it["hours"],
                        str(it.get("src", "")).replace("|", "/"),
                        str(it.get("note", "")).replace("|", "/")))
    lines.append("")

    never = data.get("not_doing") or []
    lines += [PROSE_TAIL % {
        "total": total,
        "n": len(items),
        "port": len(by_mode.get("port") or []),
        "port_h": sum(i["hours"] for i in (by_mode.get("port") or [])),
        "spec": len(by_mode.get("spec") or []),
        "spec_h": sum(i["hours"] for i in (by_mode.get("spec") or [])),
        "never": "\n".join("| %s | %s |" % (x.get("what", ""), x.get("why", ""))
                           for x in never) or "| — | — |",
    }]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 docs/CADCRAFT_MINE.md")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        if not os.path.isfile(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("docs/CADCRAFT_MINE.md 过期：跑 `python tools/gen_cadcraft_mine.py`")
            return 1
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("已写 %s" % os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
