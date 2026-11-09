"""图框 / 标题栏 / 多布局判据。"""

from __future__ import annotations

from typing import Any, Dict

from . import block_table as bt
from . import geom
from .base import Readback, verdict


def judge_titleblock(rb: Readback, *, width: float, height: float,
                     attrs: Dict[str, str],
                     insertion: tuple) -> Dict[str, Any]:
    frame = geom.judge_rect(rb, corner1=(0.0, 0.0), corner2=(width, height))
    block = bt.judge_block_insert(rb, block_name="TITLEBLOCK",
                                  attrs=attrs, insertion=insertion)
    checks: Dict[str, bool] = {}
    for key, val in frame["checks"].items():
        checks["frame." + key] = val
    for key, val in block["checks"].items():
        checks["block." + key] = val
    lines = rb.memory.count("LINE") - rb.before.count("LINE")
    checks["titleblock_lines"] = lines == 4
    detail = {"frame": frame["detail"], "block": block["detail"],
              "frame_area_expected": width * height,
              "titleblock_lines": lines}
    return verdict(checks, detail, {"frame": frame["raw"], "block": block["raw"]})


def judge_layout(rb: Readback, *, name: str,
                 recorded: Dict[str, Any]) -> Dict[str, Any]:
    tables = rb.memory.meta.get("tables") or {}
    layouts = tables.get("layouts") or {}
    vps = tables.get("layout_viewports") or {}
    re_tables = ((rb.reopened.meta.get("tables") or {})
                 if rb.reopened else {})
    re_vps = re_tables.get("layout_viewports") or {}
    before = recorded.get("viewports_before")
    after = recorded.get("viewports_after")
    checks = {
        "layout_exists": name in layouts,
        "viewport_added": (isinstance(before, int) and isinstance(after, int)
                           and after == before + 1),
        "viewport_read": vps.get(name) == after,
        "reopen": bool(name in (re_tables.get("layouts") or {})),
    }
    detail = {"name": name, "viewports_before": before, "viewports_after": after,
              "viewports_read": vps.get(name), "viewports_reopened": re_vps.get(name),
              "layouts": sorted(layouts)}
    return verdict(checks, detail, {"tables": tables})
