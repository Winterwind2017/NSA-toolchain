#!/usr/bin/env python3
"""生成 `docs/PARITY.md`：把"60 条 verified"换成可解释的覆盖率口径。

    python tools/gen_parity.py            # 写文件
    python tools/gen_parity.py --check    # 只检查（tests / pre-push 用）

四个口径（定义见生成的文档）：

    能力面覆盖   verified ÷ (verified + dead)
    内核实现覆盖 内核实现了的 verified ÷ verified
    判据强度     判据达到 L4（端到端 + 重开一致）的占比
    受众就绪度   Σ(族权重 × 族覆盖) ÷ Σ(族权重)，权重见 docs/parity_weights.yaml

数据全部来自 `docs/registry.yaml` + `src/acadkit/caps.py` + `docs/parity_weights.yaml`，
不写死数字；散文在下面的 `PROSE_*` 里。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import caps, registry                       # noqa: E402

OUT = os.path.join(ROOT, "docs", "PARITY.md")
WEIGHTS = os.path.join(ROOT, "docs", "parity_weights.yaml")

PROSE_HEAD = """# 覆盖率（parity）—— 口径与数字

> 本文件由 `python tools/gen_parity.py` 从 `docs/registry.yaml`、`src/acadkit/caps.py`、
> `docs/parity_weights.yaml` 生成。**不要手改**。

`docs/CAPABILITIES.md` 回答"能做哪些事"，这份文档回答"**做得有多全**"。

## 先看口径差异（重要）

| 项目 | 分母 | 现成数字 |
|---|---|---|
| CADCraft（复刻 AutoCAD） | AutoCAD 的 **491** 个菜单项 | 245/491 = 50%（仅 2D ≈ 65%） |
| **acadkit（本仓库）** | **自己声明的 66 条能力面** | 见下表 |

两边数字**不能直接比**。本仓库不追求 AutoCAD 全功能对齐：它只对"在真机上能自动化交付的
机械/电气制图动作"负责——交互式绘图、界面、动态块、Sheet Set 这些不在交付范围内。
所以下面的百分比说的是"**在我们承诺的范围里落实了多少**"，不是"我们等于 AutoCAD 的几成"。
"""

PROSE_TAIL = """
## 怎么用这些数字

1. **对外说明**：说"能力面覆盖 87.9%、机械制图就绪度 9x%"比说"60 条 verified"更有信息量，
   但必须同时给分母（见上一节），否则会被误读成"复刻 AutoCAD 完成 87.9%"。
2. **排优先级**：看分族表里 ratio 最低、权重最高的族——那就是下一个该做的。
3. **别用来刷分**：砍掉一条 dead（例如把它从 registry 删掉）会让覆盖率变好看，
   但那是造假。dead 条目**只能靠解锁（换路线 / 补资产）变 verified**，不能靠删除。

## 复跑

    python tools/gen_parity.py            # 重新生成
    python tools/gen_parity.py --check    # 只检查是否过期（tests 会跑这个）

改权重：编辑 `docs/parity_weights.yaml`（族名与 registry 的 `family` 一致），再重新生成。
"""


def _load_weights() -> Dict[str, Any]:
    import yaml

    with open(WEIGHTS, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _level_strength(level: str) -> int:
    """`L1–L4` → 4；`L3` → 3；认不出 → 0。"""
    nums = re.findall(r"L(\d)", level or "")
    return max((int(n) for n in nums), default=0)


def family_stats(data: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    """按族统计 verified / dead / 内核实现 / L4 判据。"""
    out: Dict[str, Dict[str, int]] = {}
    impl = set(caps.implemented_ids())
    for c in data["capabilities"]:
        fam = c.get("family") or "-"
        st = c.get("status")
        row = out.setdefault(fam, {"verified": 0, "dead": 0, "external": 0,
                                   "pending": 0, "impl": 0, "l4": 0, "total": 0})
        row["total"] += 1
        if st in row:
            row[st] += 1
        if c["id"] in impl:
            row["impl"] += 1
        cap = caps.BY_ID.get(c["id"])
        if cap is not None and _level_strength(cap.level) >= 4:
            row["l4"] += 1
    return out


def _pct(num: int, den: int) -> str:
    return "%.1f%%" % (100.0 * num / den) if den else "—"


def _ratio(row: Dict[str, int]) -> float:
    den = row["verified"] + row["dead"]
    return (row["verified"] / den) if den else 0.0


def render() -> str:
    data = registry.load()
    stats = family_stats(data)
    counts = registry.counts(data)

    surface_num = counts["verified"]
    surface_den = counts["verified"] + counts["dead"]
    impl_num = sum(1 for c in data["capabilities"]
                   if c["status"] == "verified" and c["id"] in set(caps.implemented_ids()))
    l4_num = sum(1 for c in data["capabilities"]
                 if c["status"] == "verified"
                 and caps.BY_ID.get(c["id"]) is not None
                 and _level_strength(caps.BY_ID[c["id"]].level) >= 4)

    w = _load_weights()
    audiences: List[Tuple[str, Dict[str, Any], float, List[Tuple[str, float, int]]]] = []
    for key, aud in (w.get("audiences") or {}).items():
        fams = aud.get("families") or {}
        total_w = sum(fams.values())
        score, detail = 0.0, []
        for fam, weight in fams.items():
            row = stats.get(fam)
            r = _ratio(row) if row else 0.0
            score += weight * r
            detail.append((fam, r, weight))
        detail.sort(key=lambda t: t[1])
        audiences.append((key, aud, (score / total_w) if total_w else 0.0, detail))

    lines = [PROSE_HEAD, ""]

    lines += ["## 一、四个口径", "",
              "| 口径 | 值 | 定义 |", "|---|---|---|",
              "| **能力面覆盖** | **%d/%d = %s** | verified ÷ (verified + dead)——承诺的范围里落实了多少 |"
              % (surface_num, surface_den, _pct(surface_num, surface_den)),
              "| **内核实现覆盖** | %d/%d = %s | 内核有实现的 verified ÷ verified |"
              % (impl_num, surface_num, _pct(impl_num, surface_num)),
              "| **判据强度** | %d/%d = %s | 判据达到 **L4**（建→读回→重开一致）的 verified 占比 |"
              % (l4_num, surface_num, _pct(l4_num, surface_num)),
              "| 能力条目 | %d 条（verified %d / dead %d / pending %d / external %d） | registry 原始计数 |"
              % (counts["total"], counts["verified"], counts["dead"],
                 counts["pending"], counts["external"]),
              ""]

    lines += ["## 二、按受众就绪度", "",
              "就绪度 = Σ(族权重 × 族覆盖) ÷ Σ(族权重)。权重见 `docs/parity_weights.yaml`。", "",
              "| 受众 | 就绪度 | 最拖后腿的 3 个族 |",
              "|---|---:|---|"]
    for key, aud, score, detail in audiences:
        worst = [d for d in detail if d[1] < 1.0][:3]
        worst_txt = "、".join("`%s` %s" % (f, _pct_num(r)) for f, r, _wt in worst) or "无（全部 100%）"
        lines.append("| **%s**（`%s`） | **%s** | %s |"
                     % (aud.get("label", key), key, _pct_num(score), worst_txt))
    lines.append("")
    for key, aud, score, detail in audiences:
        lines.append("- `%s`：%s" % (key, aud.get("why", "")))
    lines.append("")

    lines += ["## 三、分族明细", "",
              "| 族 | 条目 | verified | dead | 族覆盖 | 内核实现 | L4 判据 |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for fam in sorted(stats):
        row = stats[fam]
        lines.append("| `%s` | %d | %d | %d | %s | %d | %d |"
                     % (fam, row["total"], row["verified"], row["dead"],
                        _pct_num(_ratio(row)), row["impl"], row["l4"]))
    totals = {"total": counts["total"], "verified": counts["verified"],
              "dead": counts["dead"], "impl": impl_num, "l4": l4_num,
              "external": counts["external"], "pending": counts["pending"]}
    lines.append("| **合计** | **%d** | **%d** | **%d** | **%s** | **%d** | **%d** |"
                 % (totals["total"], totals["verified"], totals["dead"],
                    _pct_num(_ratio(totals)), totals["impl"], totals["l4"]))
    note = ("> `dead` 的 %d 条见 `docs/UNSUPPORTED.md`（为什么用不了）；"
            "它们什么时候值得做、要多少工时，见 `docs/GAPS.md`（缺口账本）。"
            % counts["dead"])
    lines += ["", note, ""]

    lines += [PROSE_TAIL]
    return "\n".join(lines)


def _pct_num(r: float) -> str:
    return "%.1f%%" % (100.0 * r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 docs/PARITY.md")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        if not os.path.isfile(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("docs/PARITY.md 过期：跑 `python tools/gen_parity.py`")
            return 1
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("已写 %s" % os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
