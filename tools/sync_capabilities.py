"""从已安装的 nxkit 生成技能仓库的 capabilities.json 快照。

技能是独立仓库：装到别的机器上时可能没装 nxkit。所以能力清单落成带出处的
JSON，技能自带、离线可校验；需要刷新时在本机跑一次本脚本（前提 nxkit 可 import）。

    python tools/sync_capabilities.py            # 刷新快照 + 重渲染 SKILL.md 索引
    python tools/sync_capabilities.py --check     # 只比对
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

KERNEL_REPO = "https://github.com/Winterwind2017/nxkit"

GROUP_LABEL = {
    "part": "部件", "solid": "实体", "boolean": "布尔", "curve": "曲线",
    "feature": "特征（拉伸）", "assembly": "装配", "drawing": "制图",
    "attr": "属性", "measure": "测量", "inspect": "拓扑检查",
    "export": "导出", "file": "文件",
}

# 与 docs/UNSUPPORTED.md 对应：还没打通的能力（技能里"别试这些"用）
PENDING = [
    ("feature.hole", "HolePackageBuilder 要 HolePackage.Null 哨兵，参数未摸清（通孔用 hole_cyl）"),
    ("feature.mirror", "MirrorFeatureBuilder.Plane 只读"),
    ("drawing.dimension", "part.Dimensions 的创建签名与视图绑定未验证"),
    ("measure.distance", "MeasureDistance 无 Distance 属性，Information() 返回 None"),
    ("cam.setup", "dead: 模板名全返回 None、CAMSetup 抛 1345023、CAMDataManager 只有曲线 builder"),
    ("cae.mesh", "NXOpen.CAE 绑定大、解算慢，未开始"),
    ("asm.constraints", "ConstraintCollection.CreateConstraint 不存在"),
    ("sketch.constraints", "Sketch.ConstraintGeometry 没有创建入口"),
    ("feature.chamfer_angle", "ChamferBuilder.Option/AngleExp 赋值无效"),
    ("feature.sweep", "Commit 报 Unable to approximate guide string"),
    ("feature.rib", "LoopOption 只有 Separate/SeparateOuter，链式剖面建不出来"),
    ("export.dxf", "DxfdwgCreator 需要图纸上下文"),
    ("export.parasolid", "四种方式全报 no valid export objects"),
    ("feature.thicken", "出 2 个片体或厚度变 3300 mm，语义不对"),
    ("drawing.projected_view", "ProjectedViewBuilder.Parent 只读"),
    ("drawing.section_view", "三条入口都不通：无 SectionLines、无 SectionLine 创建、SectionInView 提交为 None"),
]


def _import_nxkit():
    try:
        import nxkit
        from nxkit import caps
        from nxkit.cli import build_parser
    except Exception as exc:                              # noqa: BLE001
        raise SystemExit(
            "需要 nxkit 才能刷新能力清单（技能本身不依赖它）：\n"
            "    pip install -e <nxkit 仓库>\n"
            "或  env PYTHONPATH=<nxkit 仓库>/src python tools/sync_capabilities.py\n"
            "原始错误：%s" % exc)
    return nxkit, caps, build_parser


def _repo_root() -> str | None:
    env = os.environ.get("NXKIT_REPO")
    if env and os.path.isdir(env):
        return env
    try:
        import nxkit
        here = os.path.dirname(os.path.abspath(nxkit.__file__))
        cand = os.path.dirname(os.path.dirname(here))
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


def build_snapshot() -> dict:
    nxkit, caps, build_parser = _import_nxkit()
    verified = {c.id: c.family for c in caps.CAPS}
    levels = {c.id: c.level for c in caps.CAPS}
    sub = [a for a in build_parser()._actions if getattr(a, "choices", None)]
    cli = sorted(sub[0].choices) if sub else []
    return {
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provenance": {
            "kernel_repo": KERNEL_REPO,
            "nxkit_version": getattr(nxkit, "__version__", None),
            "kernel_commit": os.environ.get("NXKIT_COMMIT") or _kit_commit(),
            "engine": "NX 2512",
        },
        "counts": {"verified": len(verified), "families": len(set(verified.values()))},
        "verified": verified,
        "levels": levels,
        "licenses": {c.id: c.license for c in caps.CAPS if c.license},
        "cli_commands": cli,
        "pending": [{"id": i, "reason": r} for i, r in PENDING],
    }


def render_index(snap: dict) -> str:
    by_group: dict[str, list[str]] = {}
    for name, group in snap["verified"].items():
        by_group.setdefault(group, []).append(name)
    levels = snap.get("levels") or {}
    lines = [
        "本表由 `tools/sync_capabilities.py` 从 nxkit 生成的 `capabilities.json` 渲染，"
        "**不要手改**（`tests/test_skill.py` 会校验）。",
        "",
        "共 **%d** 条 verified 能力（内核 `nxkit %s`，commit `%s`，引擎 %s）。"
        "完整状态：`nxkit list`；单条跑：`nxkit cap <id>`。"
        % (len(snap["verified"]),
           snap["provenance"].get("nxkit_version") or "?",
           snap["provenance"].get("kernel_commit") or "?",
           snap["provenance"].get("engine") or "?"),
        "",
        "| 能力族 | 能力（级别） |",
        "|---|---|",
    ]
    for group in sorted(by_group, key=lambda g: (-len(by_group[g]), g)):
        names = sorted(by_group[group])
        cells = " ".join("`%s`" % n + ("（%s）" % levels[n] if levels.get(n) else "")
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
        old = open(SNAPSHOT, encoding="utf-8").read() if os.path.isfile(SNAPSHOT) else ""
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
          "| pending:", len(snap["pending"]), "| cli:", len(snap["cli_commands"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
