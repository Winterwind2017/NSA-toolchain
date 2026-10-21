"""从已安装的 swkit 生成技能仓库的 capabilities.json 快照。

这个脚本属于**技能仓库**（`ww-solidworks-automation`），不依赖内核仓库结构，
只要求 `swkit` 能被 import（`pip install -e <内核仓库>` 或 `PYTHONPATH=<内核>/src`）。

为什么要快照而不是运行时去读 registry：
技能是**独立仓库**，装到别的机器上时可能根本没装 swkit。
所以把"能力清单"落成一个带出处的 JSON，技能自带、离线可校验；
需要刷新时在本机跑一次本脚本（前提是 swkit 可用）。

用法：

    python tools/sync_capabilities.py            # 刷新快照 + 重生成技能里的索引
    python tools/sync_capabilities.py --check     # 只比对（需要 swkit 可用）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SNAPSHOT = os.path.join(ROOT, "capabilities.json")
SKILL = os.path.join(ROOT, "SKILL.md")

BEGIN = "<!-- gen:capabilities:BEGIN -->"
END = "<!-- gen:capabilities:END -->"

GROUP_LABEL = {
    "doc": "文档级", "sketch": "草图", "feature": "特征", "body": "实体",
    "surface": "曲面", "assembly": "装配", "drawing": "出图",
    "sheet_metal": "钣金", "io": "导入导出", "inspect": "只读检查",
    "view": "视图", "study": "仿真/运动", "meta": "元数据/元工具",
}


def _import_swkit():
    try:
        import swkit                                    # noqa: F401
        from swkit.registry import REGISTRY, summary    # noqa: F401
        from swkit.cli.main import build_parser         # noqa: F401
    except Exception as exc:                            # noqa: BLE001
        raise SystemExit(
            "需要 swkit 才能刷新能力清单（技能本身不依赖它）：\n"
            "    pip install -e <内核仓库>\n"
            "或  env PYTHONPATH=<内核仓库>/src python tools/sync_capabilities.py\n"
            "原始错误：%s" % exc)
    import swkit
    from swkit.registry import REGISTRY, summary
    from swkit.cli.main import build_parser
    return swkit, REGISTRY, summary, build_parser


def _kit_commit() -> str | None:
    try:
        out = subprocess.run(["git", "-C", os.environ.get("SWKIT_REPO", ""),
                              "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        c = out.stdout.strip()
        return c or None
    except Exception:                                   # noqa: BLE001
        return None


def build_snapshot() -> dict:
    swkit, REGISTRY, summary, build_parser = _import_swkit()
    s = summary()
    verified = {e.name: e.group for e in REGISTRY.values() if e.status == "verified"}
    non_verified = {e.name: e.status for e in REGISTRY.values()
                    if e.status != "verified"}
    sub = [a for a in build_parser()._actions if getattr(a, "choices", None)][0]
    return {
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provenance": {
            "kernel_repo": "https://github.com/Winterwind2017/solidworks-agent-kit",
            "swkit_version": getattr(swkit, "__version__", None),
            "kernel_commit": os.environ.get("SWKIT_COMMIT") or _kit_commit(),
        },
        "counts": {"verified": s["verified"], "unstable": s["unstable"],
                   "unverified": s["unverified"], "broken": s["broken"],
                   "implemented": s["implemented"]},
        "verified": verified,
        "non_verified": non_verified,
        "cli_commands": sorted(sub.choices),
    }


def render_index(snap: dict) -> str:
    by_group: dict[str, list[str]] = {}
    for name, group in snap["verified"].items():
        by_group.setdefault(group, []).append(name)
    total = len(snap["verified"])
    lines = [
        "本表由 `tools/sync_capabilities.py` 从 swkit 生成的 `capabilities.json` 渲染，"
        "**不要手改**（`tests/test_skill.py` 会校验）。",
        "",
        "共 **%d** 个 verified 工具（内核 `swkit %s`，commit `%s`）。"
        "完整状态：`swkit registry`。"
        % (total, snap["provenance"].get("swkit_version") or "?",
           snap["provenance"].get("kernel_commit") or "?"),
        "",
        "| 能力族 | 工具 |",
        "|---|---|",
    ]
    for group in sorted(by_group, key=lambda g: (-len(by_group[g]), g)):
        names = sorted(by_group[group])
        lines.append("| **%s**（%d） | %s |"
                     % (GROUP_LABEL.get(group, group), len(names),
                        " ".join("`%s`" % n for n in names)))
    return "\n".join(lines) + "\n"


def apply(text: str, body: str) -> str:
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0:
        raise SystemExit("SKILL.md 缺少标记 %s / %s" % (BEGIN, END))
    return text[:i] + BEGIN + "\n" + body + text[j:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    snap = build_snapshot()
    body = render_index(snap)
    with open(SKILL, encoding="utf-8") as fh:
        text = fh.read()
    new_skill = apply(text, body)
    new_snap = json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        old = open(SNAPSHOT, encoding="utf-8").read() if os.path.isfile(SNAPSHOT) else ""
        same = (old.strip() == new_snap.strip()) and (new_skill.strip() == text.strip())
        print("能力快照与技能索引一致:", same)
        return 0 if same else 4

    with open(SNAPSHOT, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_snap)
    with open(SKILL, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_skill)
    print("已刷新 capabilities.json 与 SKILL.md 能力索引")
    print("  verified:", snap["counts"]["verified"], "| cli:", len(snap["cli_commands"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
