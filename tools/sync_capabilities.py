"""从 gxkit 的 caps.py 生成技能的 capabilities.json 与 SKILL.md 能力索引。"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
KIT = pathlib.Path(os.environ.get("GXKIT_REPO", r"D:\bililive\gxkit"))
sys.path.insert(0, str(KIT / "src"))

from gxkit import caps  # noqa: E402

PENDING = [
    ("build.error_line", "行级错误定位：转换结果面板无可读文本，Progress.txt 只到阶段级"),
    ("project.check", "工程校验是两工程比对，不是校验本工程"),
    ("label.import_xml", "XML 导入能进全局标签，但样例结构体有 1 个 Error"),
    ("program.read_st", ".gx3 里 _Project.txc 是二进制，程序体在 .w3pa"),
    ("online.write", "需要真实 PLC；用户口径只做离线"),
    ("ladder.write", "梯形图编辑器是自绘控件，无法程序化写网络"),
]


def kit_commit() -> str:
    try:
        out = subprocess.run(["git", "-C", str(KIT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except Exception:
        return "unknown"


def main() -> int:
    groups: dict[str, list[str]] = {}
    catalog = {}
    for c in caps.CAPS:
        groups.setdefault(c.family, []).append(c.id)
        catalog[c.id] = {"family": c.family, "level": c.level, "title": c.title,
                         "action": c.action, "expect": c.expect, "reopen": c.reopen}
    snap = {
        "skill": "ww-gxworks-automation",
        "kernel": "gxkit",
        "kernel_version": "0.2.0",
        "kernel_commit": kit_commit(),
        "engine": "GX Works3 1.117.0.1",
        "cpu": "FX5U",
        "lang": "ST",
        "scope": "offline",
        "counts": {"verified": len(caps.CAPS),
                   "families": len(groups),
                   "pending": len(PENDING)},
        "verified": catalog,
        "families": groups,
        "pending": {k: v for k, v in PENDING},
    }
    (ROOT / "capabilities.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 能力索引（由 tools/sync_capabilities.py 生成，勿手改）",
        "",
        "共 **%d** 条已验证能力（内核 `gxkit %s`，commit `%s`，引擎 %s，机型 FX5U，语言 ST，仅离线）。"
        % (len(caps.CAPS), snap["kernel_version"], snap["kernel_commit"], snap["engine"]),
        "",
        "| id | family | level | 说明 |",
        "|---|---|---|---|",
    ]
    for c in caps.CAPS:
        lines.append("| `%s` | %s | %s | %s |" % (c.id, c.family, c.level, c.title))
    lines += ["", "## 未打通", "", "| 项 | 卡在哪 |", "|---|---|"]
    for k, v in PENDING:
        lines.append("| `%s` | %s |" % (k, v))
    (ROOT / "capabilities.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("capabilities.json / capabilities.md 已刷新：%d 条" % len(caps.CAPS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
