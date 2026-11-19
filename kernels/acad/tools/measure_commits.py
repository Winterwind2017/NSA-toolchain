#!/usr/bin/env python3
"""从 git 量"实际花了多久"，生 `docs/MEASUREMENTS.md`。

    python tools/measure_commits.py                 # 写文档
    python tools/measure_commits.py --check         # 只校验是否过期
    python tools/measure_commits.py --since '2026-11-18 21:00' --path kernels/acad

为什么需要这个：我们此前在 `docs/backlog.yaml` / `docs/cadcraft_mine.yaml` 里用
"工时"（照搬上游的**人日**估计）描述工作量，然后拿它暗示 agent 的速度——
实测下来高估两个数量级。**单位错了，结论就全错。**

现在的口径：
* **活跃分钟** = 相邻提交间隔之和，但**丢弃超过 `--idle`（默认 60 分钟）的空档**
  （那是人离开/过夜，不是工作时长）；
* 同时报**跨度**（首末提交）与**改动行数**，三者一起看才不会被单一数字误导；
* 工时字段保留，但明确标注为"上游人日 ≈ 人-小时，**不是 agent 实测**"。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kernels/acad
OUT = os.path.join(HERE, "docs", "MEASUREMENTS.md")


def _repo_root() -> str:
    res = subprocess.run(["git", "-C", HERE, "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit("不在 git 仓库里：%s" % res.stderr.strip())
    return res.stdout.strip()


ROOT = _repo_root()


@dataclass
class Commit:
    sha: str
    ts: int                     # epoch 秒
    subject: str
    added: int = 0
    removed: int = 0


def _git(args: List[str]) -> str:
    res = subprocess.run(["git", "-C", ROOT] + args, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise SystemExit("git 失败：%s\n%s" % (" ".join(args), res.stderr))
    return res.stdout


def load(since: Optional[str], path: Optional[str]) -> List[Commit]:
    args = ["log", "--pretty=format:%H|%at|%s"]
    if since:
        args += ["--since", since]
    if path:
        args += ["--", path]
    out = _git(args)
    commits: List[Commit] = []
    for line in out.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append(Commit(parts[0], int(parts[1]), parts[2]))
    commits.reverse()                                   # 时间正序
    # 逐提交统计增删行
    for c in commits:
        stat = _git(["show", "--numstat", "--format=", c.sha])
        for row in stat.splitlines():
            bits = row.split("\t")
            if len(bits) >= 2 and bits[0].isdigit():
                c.added += int(bits[0])
                c.removed += int(bits[1])
    return commits


def analyse(commits: List[Commit], idle_min: float = 60.0) -> dict:
    if not commits:
        return {"commits": 0, "active_min": 0.0, "span_min": 0.0,
                "idle_min": 0.0, "added": 0, "removed": 0, "gaps": []}
    gaps = []
    active = 0.0
    idle = 0.0
    for a, b in zip(commits, commits[1:]):
        d = (b.ts - a.ts) / 60.0
        gaps.append((a.sha[:7], b.sha[:7], round(d, 1), d > idle_min))
        if d > idle_min:
            idle += d
        else:
            active += d
    return {"commits": len(commits),
            "active_min": round(active, 1),
            "span_min": round((commits[-1].ts - commits[0].ts) / 60.0, 1),
            "idle_min": round(idle, 1),
            "added": sum(c.added for c in commits),
            "removed": sum(c.removed for c in commits),
            "gaps": gaps}


def render(since: Optional[str], path: Optional[str], idle_min: float) -> str:
    commits = load(since, path)
    a = analyse(commits, idle_min)
    lines = ["# 实测工作量（从 git 量出来的）", "",
             "> 本文件由 `python tools/measure_commits.py` 生成。**不要手改**。", "",
             "## 为什么有这个文件", "",
             "我们此前用「工时」描述工作量（照搬上游 CADCraft 的**人日**估计），",
             "并拿它暗示 agent 的速度。实测对不上，差了两个数量级；",
             "一次完整挖掘记账 **301h**，而 git 里**去掉过夜空档后的活跃时长只有约 2 小时**。",
             "", "结论：**工时是「人-小时」口径，不能用来表达 agent 吞吐**。",
             "这里改用三个可测量：活跃分钟、提交数、改动行数。", "",
             "## 口径", "",
             "| 指标 | 定义 |", "|---|---|",
             "| 活跃分钟 | 相邻提交间隔求和，**丢弃 > %g 分钟的空档** |" % idle_min,
             "| 跨度 | 首个到最后一个提交的墙钟差（含空档） |",
             "| 改动行数 | `git show --numstat` 的增/删合计（含生成物与文档） |", "",
             "## 结果", "" if not since else "范围：`--since %s`%s  \n" % (since, "" if not path else "，路径：`%s`" % path),
             "| 指标 | 数值 |", "|---|---:|",
             "| 提交数 | %d |" % a["commits"],
             "| 活跃分钟 | **%.1f**（%.2f h） |" % (a["active_min"], a["active_min"] / 60.0),
             "| 跨度分钟 | %.1f（%.2f h） |" % (a["span_min"], a["span_min"] / 60.0),
             "| 其中空档 | %.1f（%.2f h） |" % (a["idle_min"], a["idle_min"] / 60.0),
             "| 新增行 | %d |" % a["added"],
             "| 删除行 | %d |" % a["removed"],
             "| 每提交平均新增 | %.0f |" % (a["added"] / a["commits"] if a["commits"] else 0), ""]

    if a["gaps"]:
        lines += ["## 提交间隔（找出空档）", "",
                  "| 从 | 到 | 分钟 | 是否空档 |", "|---|---|---:|---|"]
        for frm, to, mins, is_idle in a["gaps"]:
            lines.append("| %s | %s | %.1f | %s |"
                         % (frm, to, mins, "**空档**" if is_idle else ""))
        lines.append("")

    lines += ["## 与「工时」的关系", "",
              "* `docs/backlog.yaml` / `docs/cadcraft_mine.yaml` 里的 `hours` 视为",
              "  **人-小时（上游口径）**，只用于「这件事对一个人类工程师大概多大」，",
              "  不要再拿它推算 agent 需要多久；",
              "* 需要对外说进度时，用本文件的**活跃分钟 + 提交数 + 改动行数**；",
              "* 真要估 agent 工作量，用**可数的动作**：真机运行次数、工具调用次数、",
              "  需要读上游代码的文件数——这三样才和 agent 的实际耗时线性相关。", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="从 git 量实测工作量")
    ap.add_argument("--since", default="2026-11-18 21:00")
    ap.add_argument("--path", default="kernels/acad")
    ap.add_argument("--idle", type=float, default=60.0)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render(args.since, args.path, args.idle)
    if args.check:
        if not os.path.isfile(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("docs/MEASUREMENTS.md 过期：跑 tools/measure_commits.py")
            return 1
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("已写 %s" % os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
