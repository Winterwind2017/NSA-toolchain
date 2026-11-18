#!/usr/bin/env python3
"""生成 `docs/BACKLOG.md`：挖掘全量清单（先看总量，再决定挖哪个）。

    python tools/gen_backlog.py            # 写文件
    python tools/gen_backlog.py --check    # 只检查（tests / pre-push）

数据源：`docs/backlog.yaml`（人工维护的计划清单）。
交叉校验：与 `docs/gaps_meta.yaml` 同 id 的工时必须相等；与 registry 的
`verified` 不能重复（已经能用的能力不该再出现在待挖清单里）。

规则（与用户约定，2026-11-18）：挖掘类任务**先出全量清单再动手**，
不要做完一步才建议下一步——所以这份文档必须在任何一条能力动工前就存在。
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import registry                        # noqa: E402

OUT = os.path.join(ROOT, "docs", "BACKLOG.md")
SRC = os.path.join(ROOT, "docs", "backlog.yaml")
GAPS = os.path.join(ROOT, "docs", "gaps_meta.yaml")

TIER_ORDER = ("T1", "T2", "T3")
SOURCE_LABEL = {
    "cc": "CADCraft 启发",
    "cc/pain": "CADCraft 启发 + 自家踩坑",
    "ax": "AutoCAD 能力面",
    "pain": "自家踩坑",
    "dom": "行业/领域需求",
    "eng": "工程化常识",
}
SOURCE_ORDER = ("cc", "cc/pain", "pain", "ax", "dom", "eng")
TIER_LABEL = {
    "T1": "T1 必做 —— 缺了不能叫「能用」",
    "T2": "T2 应该做 —— 专业交付质量",
    "T3": "T3 可以做 —— 差异化",
}

PROSE_HEAD = """# 挖掘全量清单（backlog）

> 本文件由 `python tools/gen_backlog.py` 从 `docs/backlog.yaml` 生成。**不要手改**。
> 最近更新：%(updated)s

## 读法

这份文档回答一个问题：**要达到"理想效果"，一共还有多少东西能挖、要多少工时。**
它不是排期表——排期看 `docs/GAPS.md`（当前 8 周内要动的子集）。

| 文档 | 回答什么 |
|---|---|
| `CAPABILITIES.md` | 现在能做什么（%(done)d 条 verified） |
| **`BACKLOG.md`（本文）** | **还能挖什么、总量多少、哪些明确不做** |
| `GAPS.md` | 眼下先做哪几条、怎么绕 |
| `UNSUPPORTED.md` | 挖不动的原因与证据 |

## 理想效果（Definition of Done）

%(ideal)s
"""

PROSE_TAIL = """
## 工时怎么读

* 单位是 **agent-hours**（本仓库现有实现速度下的估计），±50%%，**用于比较与预算，不用于承诺**；
* 一条能力的实际成本 ≈ 实现 + 判据 + 踩坑，判据往往比实现贵；
* 结论：**%(total)gh 不是"再干 %(weeks).0f 周"**，而是"按当前节奏约 %(months).1f 个月的单人 agent 工作量"，
  其中 T1 部分（%(t1)gh）才是"能不能用"的分水岭。

## 与 registry 的关系

清单里的 id 一旦落地，就应该出现在 `docs/registry.yaml` 里并标 `verified`；
反过来，`verified` 的能力**不应**再出现在本清单（测试会校验，防止虚报进度）。

## 明确不做

| 不做 | 为什么 |
|---|---|
%(never)s
"""


def _load(path: str) -> Dict[str, Any]:
    import yaml

    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build() -> Dict[str, Any]:
    data = _load(SRC)
    items = list(data.get("items") or [])
    areas = {a["key"]: a for a in (data.get("areas") or [])}
    verified = {c["id"] for c in registry.load()["capabilities"]
                if c.get("status") == "verified"}

    # 与 gaps_meta 的工时对齐
    gaps = {}
    if os.path.isfile(GAPS):
        for g in (_load(GAPS).get("items") or []):
            gaps[g["id"]] = float(g.get("hours") or 0)

    seen = set()
    for it in items:
        cid = it["id"]
        if cid in seen:
            raise SystemExit("backlog.yaml 里 %s 重复" % cid)
        seen.add(cid)
        if cid in verified:
            raise SystemExit("%s 已经是 verified，不该再出现在挖掘清单里" % cid)
        if it.get("area") not in areas:
            raise SystemExit("%s 的 area=%r 没在 areas 里登记" % (cid, it.get("area")))
        if it.get("tier") not in TIER_ORDER:
            raise SystemExit("%s 的 tier=%r 非法" % (cid, it.get("tier")))
        if cid in gaps and float(it.get("hours") or 0) != gaps[cid]:
            raise SystemExit("%s 工时与 gaps_meta 不一致：%s vs %s"
                             % (cid, it.get("hours"), gaps[cid]))
        it["hours"] = float(it.get("hours") or 0)
        it["impact"] = int(it.get("impact") or 1)

    return {"data": data, "items": items, "areas": areas, "gaps": gaps}


def render() -> str:
    built = build()
    data, items, areas, gaps = (built["data"], built["items"],
                                built["areas"], built["gaps"])
    done = len([c for c in registry.load()["capabilities"]
                if c.get("status") == "verified"])
    total = sum(i["hours"] for i in items)
    by_tier = {t: [i for i in items if i["tier"] == t] for t in TIER_ORDER}
    tier_hours = {t: sum(i["hours"] for i in v) for t, v in by_tier.items()}

    lines = [PROSE_HEAD % {
        "updated": data.get("updated_at", "—"),
        "done": done,
        "ideal": str(data.get("ideal_state", "")).strip(),
    }, ""]

    lines += ["## 一、总量", "",
              "| 门槛 | 项数 | 工时 | 占比 |", "|---|---:|---:|---:|"]
    for t in TIER_ORDER:
        lines.append("| %s | %d | %gh | %.0f%% |"
                     % (TIER_LABEL[t], len(by_tier[t]), tier_hours[t],
                        100.0 * tier_hours[t] / total if total else 0))
    lines.append("| **合计** | **%d** | **%gh** | 100%% |" % (len(items), total))
    lines += ["",
              "> 其中落在当前 `GAPS.md` 里的（眼下就要动的）：**%d 条 / %gh**；"
              "也就是说 GAPS 只占全量的 **%.0f%%**——"
              "「先做哪几条」和「一共多少」是两个问题，不要混。"
              % (len([i for i in items if i["id"] in gaps]),
                 sum(gaps[i["id"]] for i in items if i["id"] in gaps),
                 100.0 * sum(gaps[i["id"]] for i in items if i["id"] in gaps) / total
                 if total else 0), ""]

    lines += ["## 二、按域", "",
              "| 域 | 已有能力 | 待挖项 | 待挖工时 | 为什么这个域重要 |",
              "|---|---:|---:|---:|---|"]
    for key, area in areas.items():
        mine = [i for i in items if i["area"] == key]
        if not mine and not area.get("have"):
            continue
        lines.append("| %s（`%s`） | %s | %d | %gh | %s |"
                     % (area.get("title", key), key, area.get("have", "—"),
                        len(mine), sum(i["hours"] for i in mine),
                        area.get("why", "")))
    lines.append("")

    from collections import Counter, defaultdict
    by_src = defaultdict(list)
    for it in items:
        by_src[it.get("source") or "ax"].append(it)
    lines += ["## 三、来源：到底多少是「跟 CADCraft 学的」", "",
              "这一节回答一个常见误解：**这份清单不是 CADCraft 的待办表**。", "",
              "| 来源 | 项数 | 工时 | 占比 | 说明 |",
              "|---|---:|---:|---:|---|"]
    for key in SOURCE_ORDER:
        group = by_src.get(key) or []
        if not group:
            continue
        h = sum(i["hours"] for i in group)
        note = {
            "cc": "真正从 CADCraft 的方法/教训里来的（含它踩过的坑）",
            "cc/pain": "两边都撞上的同一类问题",
            "pain": "我们在真 AutoCAD 上自己踩的（CADCraft 不用 COM，教不了）",
            "ax": "AutoCAD 自身能力面（驱动真机才需要，CADCraft 那套没有）",
            "dom": "机械/电气行业需求（CADCraft 完全没有）",
            "eng": "工程化常识（与 CAD 无关）",
        }.get(key, "")
        lines.append("| %s | %d | %gh | %.0f%% | %s |"
                     % (SOURCE_LABEL.get(key, key), len(group), h,
                        100.0 * h / total if total else 0, note))
    lines.append("")
    cc_share = sum(i["hours"] for i in (by_src.get("cc") or [])
                   + (by_src.get("cc/pain") or []))
    lines += ["> 结论：CADCraft 直接贡献 **%gh / %.0f%%**；剩下 %.0f%% 与它无关。"
              % (cc_share, 100.0 * cc_share / total if total else 0,
                 100.0 - (100.0 * cc_share / total if total else 0)),
              "> 能学的主要是**方法与教训**，不是代码：它的几何内核/DXF 读写对我们是无用的",
              "> （我们把几何交给 AutoCAD），而它的「真实语料」「无损存盘」两条教训恰好补上了我们的盲区。",
              ""]

    lines += ["## 四、全量明细", "",
              "排序：门槛（T1→T3）→ 影响分降序 → 工时升序。",
              ""]
    for t in TIER_ORDER:
        group = sorted(by_tier[t], key=lambda i: (-i["impact"], i["hours"], i["id"]))
        if not group:
            continue
        lines += ["### %s（%d 项 / %gh）" % (TIER_LABEL[t], len(group), tier_hours[t]), "",
                  "| # | 能力 | 干什么 | 来源 | 影响 | 工时 | 关键风险 / 说明 | 在 GAPS 里 |",
                  "|---|---|---|---|---:|---:|---|---|"]
        for n, it in enumerate(group, 1):
            lines.append("| %d | `%s` | %s | %s | %d | %gh | %s | %s |"
                         % (n, it["id"], it.get("title", ""),
                            SOURCE_LABEL.get(it.get("source"), it.get("source") or "—"),
                            it["impact"], it["hours"],
                            str(it.get("note", "")).replace("|", "/"),
                            "是" if it["id"] in gaps else "—"))
        lines.append("")

    never = data.get("not_doing") or []
    total_months = total / 160.0
    lines += [PROSE_TAIL % {
        "total": total,
        "weeks": total / 40.0,
        "months": total_months,
        "t1": tier_hours["T1"],
        "never": "\n".join("| %s | %s |" % (n.get("what", ""), n.get("why", ""))
                           for n in never) or "| — | — |",
    }]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 docs/BACKLOG.md")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        if not os.path.isfile(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("docs/BACKLOG.md 过期：跑 `python tools/gen_backlog.py`")
            return 1
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("已写 %s" % os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
