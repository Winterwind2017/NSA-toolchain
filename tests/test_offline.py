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


def test_hole_wizard_rejects_wrong_diameter() -> None:
    """孔向导不解析规格表（几何恒 Ø50.8）——判据必须把它拦下来。

    这是 2026-11-06 修掉的一个"假通过"：旧判据只看"体积变小"，
    于是 M6 请求被做成 Ø50.8 也照样 ok=True。现在用去除体积反算孔径
    `d = 2·sqrt(V/(π·depth))`，和 TAP_DRILL_MM 比，比不过就判失败。
    """
    import math
    import types

    from swkit.verified import features

    def run(v0: float, v1: float, size: str, depth: float, through: bool = False):
        doc = types.SimpleNamespace(v0=v0, v1=v1, call=0)
        features._volume_mm3 = lambda d: (d.v0 if d.call == 0 else d.v1)
        features.shape_counts = lambda d: {
            "features": 1 if d.call == 0 else 2
        }

        def fake(**kwargs):
            doc.call = 1

        features._kernel = lambda: types.SimpleNamespace(hole_wizard=fake)
        return features.hole_wizard(doc, size=size, depth_mm=depth, through_all=through)

    good = math.pi / 4 * 5.0 ** 2 * 12
    ok = run(48000.0, 48000.0 - good, "M6", 12.0)
    assert ok["ok"] is True
    assert ok["checks"]["diameter_matches"] is True
    assert abs(ok["detail"]["hole_diameter_mm"] - 5.0) < 1e-6

    wrong = math.pi / 4 * 50.8 ** 2 * 12
    bad = run(200000.0, 200000.0 - wrong, "M6", 12.0)
    assert bad["ok"] is False
    assert bad["checks"]["diameter_matches"] is False
    assert "RECIPES.md" in bad["detail"]["delegate"]

    blind_unknown = run(48000.0, 47000.0, "M6", 12.0, through=True)
    assert blind_unknown["ok"] is False
    assert blind_unknown["checks"]["diameter_verified"] is False


def test_tap_drill_table_matches_docs() -> None:
    """规格表必须和 docs/RECIPES.md §3 一致（M3–M12）。"""
    from swkit.verified.features import TAP_DRILL_MM

    assert TAP_DRILL_MM == {"M3": 2.5, "M4": 3.3, "M5": 4.2, "M6": 5.0,
                            "M8": 6.8, "M10": 8.5, "M12": 10.2}


def test_no_phantom_tool_names() -> None:
    """registry/docs 里不许出现"不存在的工具名"（sw_threaded_hole 曾长期被引用）。"""
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1]
    phantom = "sw_threaded_hole"
    offenders = []
    for path in list(root.glob("src/**/*.py")) + list(root.glob("docs/*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if phantom in line and "没有" not in line and "不存在" not in line:
                offenders.append("%s:%d" % (path.name, lineno))
    assert not offenders, offenders
