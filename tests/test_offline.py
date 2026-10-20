"""tests/test_offline.py —— 不需要 SolidWorks 的契约测试

这些是"仓库自洽性"检查：清单口径、标记常量、CLI/MCP 结构。它们保证
**文档承诺的东西在代码里真的存在**，但不断言任何 SolidWorks 行为
（那部分在 `test_live.py`，默认跳过）。
"""

from __future__ import annotations

import re

import pytest

import swkit
from swkit.registry import REGISTRY, META_TOOLS, summary


def test_version_is_string() -> None:
    assert isinstance(swkit.__version__, str)
    assert re.match(r"^\d+\.\d+\.\d+", swkit.__version__)


def test_registry_status_values() -> None:
    allowed = {"verified", "unstable", "unverified", "broken"}
    bad = {e.name: e.status for e in REGISTRY.values() if e.status not in allowed}
    assert not bad, bad


def test_every_verified_entry_has_evidence() -> None:
    missing = [e.name for e in REGISTRY.values()
               if e.status == "verified" and not (e.evidence or "").strip()]
    assert not missing, "verified 条目必须有判据：%s" % missing


def test_implemented_implies_verified() -> None:
    bad = [e.name for e in REGISTRY.values()
           if e.implemented and e.status != "verified"]
    assert not bad, "implemented 必须是 verified：%s" % bad


def test_summary_matches_registry() -> None:
    counts = summary()
    for status in ("verified", "unstable", "unverified", "broken"):
        expected = sum(1 for e in REGISTRY.values() if e.status == status)
        assert counts[status] == expected, status
    assert counts["implemented"] == sum(1 for e in REGISTRY.values() if e.implemented)
    assert counts["verified_not_implemented"] == counts["verified"] - counts["implemented"]
    assert counts["meta_tools"] == len(META_TOOLS)


def test_marks_are_inverted_between_feature_and_component() -> None:
    """这是本仓库最贵的知识：两种阵列的标记是**相反**的。"""
    from swkit.core import marks

    assert marks.FEATURE_TO_PATTERN == 4
    assert marks.FEATURE_DIR1 == 1
    assert marks.COMPONENT_TO_PATTERN == 1
    assert marks.COMPONENT_DIR1 == 2
    # 绝不能相等，否则两种阵列会互相踩
    assert marks.FEATURE_TO_PATTERN != marks.COMPONENT_TO_PATTERN
    assert marks.FEATURE_DIR1 != marks.COMPONENT_DIR1


def test_cli_exposes_every_subcommand_with_handler() -> None:
    from swkit.cli.main import build_parser

    parser = build_parser()
    actions = [a for a in parser._actions if getattr(a, "choices", None)]
    choices = []
    for act in actions:
        if isinstance(act.choices, dict):
            choices.extend(act.choices.keys())
    assert len(choices) >= 35, "子命令数量异常：%d" % len(choices)
    for name in ("bbox", "shell", "pattern-component", "mirror-component",
                 "sim", "motion", "docs", "new-drawing", "hole-table", "balloon"):
        assert name in choices, name


def test_mcp_server_registers_tools() -> None:
    pytest.importorskip("mcp.server.fastmcp")
    import swkit.mcp.server as server

    tools = [n for n in dir(server) if n.startswith("sw_")]
    assert len(tools) >= 40, "MCP 工具数量异常：%d" % len(tools)
    for required in ("sw_pattern_component", "sw_mirror_component",
                     "sw_bounding_box", "sw_docs_stats", "sw_add_balloon"):
        assert required in tools, required


def test_drawing_view_names_are_localized() -> None:
    from swkit.verified.drawing import VIEW_MAP

    assert VIEW_MAP["front"] == "*前视"
    assert all(v.startswith("*") for v in VIEW_MAP.values())


def test_doctor_script_declares_all_checks() -> None:
    """换机器自检脚本必须存在，且覆盖 5 项关键检查（远端协议/SSH key 等）。

    `scripts/doctor.py` 是**跟代码走**的提醒：换机器 clone 下来就能跑，
    不依赖任何本地记忆。这里只做静态契约（不真的跑 ssh/git）。
    """
    import pathlib

    p = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "doctor.py"
    assert p.is_file(), "缺少 scripts/doctor.py"
    text = p.read_text(encoding="utf-8")
    for fn in ("check_python", "check_remote", "check_ssh", "check_comtypes",
               "check_solidworks"):
        assert fn in text, "doctor 缺少 %s" % fn
    # 必须给出 SSH 与 HTTPS 的修法，否则提醒不可执行
    assert "ssh-keygen" in text
    assert "set-url origin" in text

def test_repo_carries_cross_machine_reminder() -> None:
    """换机器提醒必须**跟仓库走**：AGENTS.md + pre-push hook 都要在。

    用户要求"在任何其它电脑上都提醒配 SSH key"。本地记忆跟不了换机器，
    所以载体是仓库文件本身：AGENTS.md（人/agent 第一页）与
    scripts/hooks/pre-push（真正的拦截器）。
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    agents = root / "AGENTS.md"
    hook = root / "scripts" / "hooks" / "pre-push"
    assert agents.is_file(), "缺少 AGENTS.md"
    assert hook.is_file(), "缺少 scripts/hooks/pre-push"
    a = agents.read_text(encoding="utf-8")
    h = hook.read_text(encoding="utf-8")
    assert "scripts/doctor.py" in a and "ssh-keygen" in a
    assert "ssh-keygen" in h and "remote set-url" in h
    # hook 必须能被 install_hooks.py 识别为"自己装的"（幂等）
    assert "managed by swkit scripts/install_hooks.py" in h