#!/usr/bin/env python3
"""生成 `docs/GAPS.md`：缺口账本（排序 + 工时 + 解锁条件）。

    python tools/gen_gaps.py            # 写文件
    python tools/gen_gaps.py --check    # 只检查（tests / pre-push 用）

数据来源：
    `docs/registry.yaml`    —— dead 条目的 id / 族 / 卡点 / 替代（唯一事实来源）
    `docs/gaps_meta.yaml`   —— 影响分、预估工时、受众、排序理由、解锁条件

两边必须对上：registry 里每条 dead 都必须在 meta 里有条目（漏了直接报错），
meta 里 kind=dead 的 id 也必须真的在 registry 里（防止改名后留下孤儿）。
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import registry                       # noqa: E402

OUT = os.path.join(ROOT, "docs", "GAPS.md")
META = os.path.join(ROOT, "docs", "gaps_meta.yaml")

AUD_LABEL = {"mech": "机械", "elec": "电气", "general": "通用"}

PROSE_HEAD = """# 缺口账本（gaps）

> 本文件由 `python tools/gen_gaps.py` 从 `docs/registry.yaml` + `docs/gaps_meta.yaml` 生成。
> **不要手改**：改 meta（影响分/工时/解锁条件），再重新生成。

三个文档的分工：

| 文档 | 回答的问题 |
|---|---|
| `CAPABILITIES.md` | 现在**能做**什么 |
| `UNSUPPORTED.md` | 用不了的**为什么**用不了（卡在哪一层、证据、复核条件） |
| **`GAPS.md`（本文）** | 还缺什么、**先做哪个**、要多少工时、**解锁需要什么** |

## 工时口径

`hours` 是 **agent-hours**（本仓库现有实现速度下的估计），不是人日。用来**排序和做预算**，
不用于对外承诺；±50% 的误差可接受。参照 CADCraft 的 calibration 思路
（每个选项/小修 0.3–0.7h，中等特性 2–5h，子系统 15–100h），但数字是本仓库自己的估计。

排序规则：**影响分降序 → 工时升序 → id 字典序**（同样重要时先做便宜的）。
`hours: 0` 表示"不再追"，旁边会标 **不做**。
"""

PROSE_TAIL = """
## 建议路线

1. **先做「换路线」能一次解锁的 4 条**：`dim.associative`、`block.edit_inplace`、
   `layer.state`、`solid.revolve` 全都卡在 ActiveX 够不着，而 **.NET 插件（进程内）**
   一条路能同时解决。插件骨架是一次性投入，之后每条约 4–8h。
2. **再做「直接实现」的低成本项**：`dim.update`(4h)、`interfere`(2h)、`plot.style`(12h)
   —— 不依赖新路线，做完立刻改善交付质量。
3. **`constraint.geometric` 不做**：完整版 AutoCAD 没有，属 Mechanical 专有，不在承诺范围。
4. **`view.projection_builtin` 不再追**：自建 CSG 投影已 verified，官方命令缺失不影响交付。

## 复核触发条件

跟 `UNSUPPORTED.md` 一致：换 AutoCAD 版本（R26+）/ 换机器 / Autodesk 更新 ActiveX 类型库时，
重新跑 `python tests/live_judges.py --only <族>`，确认哪些结论仍然成立。
**.NET 插件如果落地了，这几条 dead 要重测并改成 verified**——不要直接沿用本表的"不可用"。
"""


def _load_meta() -> Dict[str, Any]:
    import yaml

    with open(META, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _impact_bar(n: int) -> str:
    return "●" * n + "○" * (5 - n)


def build_rows() -> List[Dict[str, Any]]:
    data = registry.load()
    dead = {c["id"]: c for c in data["capabilities"] if c.get("status") == "dead"}
    meta = _load_meta()
    items = meta.get("items") or []

    seen = set()
    rows: List[Dict[str, Any]] = []
    for it in items:
        cid = it["id"]
        if cid in seen:
            raise SystemExit("gaps_meta.yaml 里 %s 重复" % cid)
        seen.add(cid)
        kind = it.get("kind", "dead")
        if kind == "dead" and cid not in dead:
            raise SystemExit("%s 标成 dead，但 registry 里没有这条（或不是 dead）" % cid)
        src = dead.get(cid, {})
        rows.append({
            "id": cid,
            "kind": kind,
            "family": src.get("family", "—"),
            "impact": int(it.get("impact", 1)),
            "hours": float(it.get("hours", 0)),
            "audience": list(it.get("audience") or []),
            "why": it.get("why", ""),
            "unblock": it.get("unblock", ""),
            "alt": it.get("alt", "") or src.get("judge", ""),
        })

    missing = sorted(set(dead) - seen)
    if missing:
        raise SystemExit("registry 里这些 dead 没进 gaps_meta.yaml：%r" % missing)

    rows.sort(key=lambda r: (-r["impact"], r["hours"], r["id"]))
    return rows


def render() -> str:
    rows = build_rows()
    dead_rows = [r for r in rows if r["kind"] == "dead"]
    planned = [r for r in rows if r["kind"] == "planned"]
    want = [r for r in rows if r["hours"] > 0]
    total = sum(r["hours"] for r in want)

    lines = [PROSE_HEAD, ""]
    lines += ["## 一、全部缺口（按影响排序）", "",
              "| # | 缺口 | 类型 | 影响 | 工时 | 受众 | 为什么排这儿 | 解锁条件 | 现在怎么办 |",
              "|---|---|---|---|---:|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        hours = "**不做**" if r["hours"] <= 0 else ("%gh" % r["hours"] if r["hours"] % 1 else "%dh" % r["hours"])
        aud = "、".join(AUD_LABEL.get(a, a) for a in r["audience"]) or "—"
        lines.append("| %d | `%s` | %s | %s %d | %s | %s | %s | %s | %s |"
                     % (i, r["id"], "dead" if r["kind"] == "dead" else "planned",
                        _impact_bar(r["impact"]), r["impact"], hours, aud,
                        _esc(r["why"]), _esc(r["unblock"]), _esc(r["alt"])))
    lines += ["",
              "合计：**%d 条**（dead %d / planned %d），需要工时的 %d 条共 **%gh**。"
              % (len(rows), len(dead_rows), len(planned), len(want), total), ""]

    lines += ["## 二、dead：本机拿不到官方路径（墙）", "",
              "这些不是「没时间做」，是「这条路走不通」。要么换路线（.NET 插件 / ObjectARX），"
              + "要么承认不做。逐条卡点与证据见 `docs/UNSUPPORTED.md`。", ""]
    for r in dead_rows:
        lines.append("- **`%s`**（%s，影响 %d/5）：%s"
                     % (r["id"], r["family"], r["impact"], _esc(r["why"])))
    lines.append("")

    lines += ["## 三、planned：能做但没做（账）", ""]
    if not planned:
        lines.append("（当前没有登记 planned 项）")
    for r in planned:
        hours = "**不做**" if r["hours"] <= 0 else "%gh" % r["hours"]
        lines.append("- **`%s`**（%s，影响 %d/5，%s）：%s"
                     % (r["id"], r["family"], r["impact"], hours, _esc(r["why"])))
    lines.append("")

    lines += [PROSE_TAIL]
    return "\n".join(lines)


def _esc(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ").strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 docs/GAPS.md")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        if not os.path.isfile(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("docs/GAPS.md 过期：跑 `python tools/gen_gaps.py`")
            return 1
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("已写 %s" % os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
