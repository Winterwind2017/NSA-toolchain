"""离线校验：技能文档必须与 capabilities.json 快照一致。

不依赖 nxkit、不启动 NX。
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


def test_snapshot_wellformed() -> None:
    with open(os.path.join(ROOT, "capabilities.json"), encoding="utf-8") as fh:
        snap = json.load(fh)
    assert snap["schema"] == 1
    assert snap["verified"], "verified 不能为空"
    assert snap["cli_commands"], "cli_commands 不能为空"
    assert snap["counts"]["verified"] == len(snap["verified"])
    assert snap["provenance"].get("kernel_repo")
    for cid in snap["verified"]:
        assert snap["levels"].get(cid), cid


def test_index_is_fresh() -> None:
    import sync_capabilities as S

    with open(os.path.join(ROOT, "capabilities.json"), encoding="utf-8") as fh:
        snap = json.load(fh)
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        text = fh.read()
    expected = S.apply(text, S.render_index(snap))
    assert expected.strip() == text.strip(), (
        "SKILL.md 能力索引过期（跑 tools/sync_capabilities.py 重生成）")


def test_name_is_ww_prefix() -> None:
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        head = fh.read(400)
    assert "name: ww-nx-automation" in head
