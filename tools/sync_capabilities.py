"""从已安装的 acadkit 生成技能仓库的 capabilities.json 快照。

这个脚本属于**技能仓库**（`ww-autocad-automation`），不依赖内核仓库结构，
只要求 `acadkit` 能被 import（`pip install -e <内核仓库>` 或
`PYTHONPATH=<内核仓库>/src`）。

为什么要快照而不是运行时去读 registry：
技能是**独立仓库**，装到别的机器上时可能根本没装 acadkit。
所以把"能力清单"落成一个带出处的 JSON，技能自带、离线可校验；
需要刷新时在本机跑一次本脚本（前提是 acadkit 可用）。

用法：

    python tools/sync_capabilities.py            # 刷新快照 + 重生成技能里的索引
    python tools/sync_capabilities.py --check     # 只比对（需要 acadkit 可用）
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

KERNEL_REPO = "https://github.com/Winterwind2017/autocad-agent-kit"

GROUP_LABEL = {
    "geom": "几何", "text": "文字", "dim": "标注", "gdt": "形位公差",
    "symbol": "符号", "table": "表格", "block": "块", "frame": "图框/布局",
    "layer": "图层", "env": "系统变量/样式", "solid": "实体",
    "boolean": "布尔/剖切", "view": "视图", "projection": "投影",
    "lisp": "LISP", "export": "导出", "pid": "P&ID", "ae": "电气数据",
    "plc": "PLC", "envvars": "系统变量",
}


def _import_acadkit():
    try:
        import acadkit                                     # noqa: F401
        from acadkit import caps, registry                # noqa: F401
        from acadkit.cli.main import build_parser         # noqa: F401
    except Exception as exc:                              # noqa: BLE001
        raise SystemExit(
            "需要 acadkit 才能刷新能力清单（技能本身不依赖它）：\n"
            "    pip install -e <内核仓库>\n"
            "或  env PYTHONPATH=<内核仓库>/src python tools/sync_capabilities.py\n"
            "原始错误：%s" % exc)
    import acadkit
    from acadkit import caps, registry
    from acadkit.cli.main import build_parser
    return acadkit, caps, registry, build_parser


def _repo_root() -> str | None:
    env = os.environ.get("ACADKIT_REPO")
    if env and os.path.isdir(env):
        return env
    try:
        import acadkit
        here = os.path.dirname(os.path.abspath(acadkit.__file__))   # …/src/acadkit
        cand = os.path.dirname(os.path.dirname(here))              # 仓库根
        return cand if os.path.isdir(os.path.join(cand, "docs")) else None
    except Exception:                                     # noqa: BLE001
        return None


def _kit_commit() -> str | None:
    repo = _repo_root()
    if not repo:
        return None
    try:
        out = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:                                     # noqa: BLE001
        return None


def _cli_commands(build_parser) -> list[str]:
    parser = build_parser()
    for action in parser._actions:
        if getattr(action, "choices", None):
            return sorted(action.choices)
    return []


def build_snapshot() -> dict:
    acadkit, capsmod, registrymod, build_parser = _import_acadkit()
    data = registrymod.load()
    caps = list(capsmod.CAPS)
    verified = {c["id"]: str(c.get("family") or "") for c in data["capabilities"]
                if c.get("status") == "verified"}
    non_verified = {c["id"]: str(c.get("status") or "")
                    for c in data["capabilities"]
                    if c.get("status") in ("dead", "external")}
    levels = {c.id: c.level for c in caps}
    by_status = registrymod.counts(data)
    negatives = [c.id for c in caps if c.is_negative or c.expect == "fail"]
    return {
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provenance": {
            "kernel_repo": KERNEL_REPO,
            "acadkit_version": getattr(acadkit, "__version__", None),
            "kernel_commit": os.environ.get("ACADKIT_COMMIT") or _kit_commit(),
        },
        "counts": {
            "verified": len(verified),
            "dead": by_status.get("dead", 0),
            "external": by_status.get("external", 0),
            "registry": by_status.get("total", 0),
            "caps": len(caps),
            "negatives": len(negatives),
        },
        "verified": verified,
        "non_verified": non_verified,
        "levels": levels,
        "negative_controls": sorted(negatives),
        "cli_commands": _cli_commands(build_parser),
    }


def render_index(snap: dict) -> str:
    by_group: dict[str, list[str]] = {}
    for name, group in snap["verified"].items():
        by_group.setdefault(group, []).append(name)
    lines = [
        "本表由 `tools/sync_capabilities.py` 从 acadkit 生成的 `capabilities.json` 渲染，"
        "**不要手改**（`tests/test_skill.py` 会校验）。",
        "",
        "共 **%d** 条 verified 能力（内核 `acadkit %s`，commit `%s`）。"
        "完整状态：`acadkit registry`；单条跑：`acadkit cap <id>`。"
        % (len(snap["verified"]),
           snap["provenance"].get("acadkit_version") or "?",
           snap["provenance"].get("kernel_commit") or "?"),
        "",
        "| 能力族 | 能力（级别） |",
        "|---|---|",
    ]
    levels = snap.get("levels") or {}
    for group in sorted(by_group, key=lambda g: (-len(by_group[g]), g)):
        names = sorted(by_group[group])
        cells = " ".join(
            "`%s`" % n + ("（%s）" % levels[n] if levels.get(n) else "")
            for n in names)
        lines.append("| **%s**（%d） | %s |"
                     % (GROUP_LABEL.get(group, group), len(names), cells))
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
        old = (open(SNAPSHOT, encoding="utf-8").read()
               if os.path.isfile(SNAPSHOT) else "")
        same = (old.strip() == new_snap.strip()
                and new_skill.strip() == text.strip())
        print("能力快照与技能索引一致:", same)
        return 0 if same else 4

    with open(SNAPSHOT, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_snap)
    with open(SKILL, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_skill)
    print("已刷新 capabilities.json 与 SKILL.md 能力索引")
    print("  verified:", snap["counts"]["verified"],
          "| non_verified:", len(snap["non_verified"]),
          "| cli:", len(snap["cli_commands"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
