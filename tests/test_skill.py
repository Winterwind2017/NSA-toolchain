"""离线校验：技能文档必须与 capabilities.json 快照一致。

不依赖 swkit、不启动 SolidWorks——技能要能在任何机器上被校验。
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def test_check_skill_passes() -> None:
    import check_skill

    problems = check_skill.check()
    assert not problems, "技能校验失败：\n  - " + "\n  - ".join(problems)


def test_snapshot_is_wellformed() -> None:
    with open(os.path.join(ROOT, "capabilities.json"), encoding="utf-8") as fh:
        snap = json.load(fh)
    assert snap["schema"] == 1
    assert snap["verified"], "verified 不能为空"
    assert snap["cli_commands"], "cli_commands 不能为空"
    # 计数必须自洽
    counts = snap["counts"]
    assert counts["verified"] == len(snap["verified"])
    assert counts["verified"] + len(snap["non_verified"]) == (
        counts["verified"] + counts["unstable"] + counts["unverified"] + counts["broken"])
    assert snap["provenance"].get("kernel_repo")


def test_index_is_fresh() -> None:
    """SKILL.md 里的能力索引必须与 capabilities.json 渲染结果一致。"""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_capabilities as S

    with open(os.path.join(ROOT, "capabilities.json"), encoding="utf-8") as fh:
        snap = json.load(fh)
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        text = fh.read()
    expected = S.apply(text, S.render_index(snap))
    assert expected.strip() == text.strip(), (
        "SKILL.md 能力索引过期（跑 tools/sync_capabilities.py 重生成）")


def test_name_is_ww_prefix() -> None:
    """技能名必须是 ww-solidworks-automation（与内核仓库解耦后定的名字）。"""
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        head = fh.read(400)
    assert "name: ww-solidworks-automation" in head
