"""系统变量 / 标注样式判据。"""

from __future__ import annotations

from typing import Any, Dict

from .base import Readback, close, verdict


def judge_sysvar(recorded: Dict[str, Any], *, name: str,
                 expected: Any) -> Dict[str, Any]:
    """设置 → 读回 → 还原 → 再读回。三条都从 AutoCAD 读，不看返回值。"""
    before = recorded.get("before")
    after = recorded.get("after")
    restored = recorded.get("restored")

    def same(a: Any, b: Any) -> bool:
        if isinstance(b, (int, float)) and isinstance(a, (int, float)):
            return close(a, b, 1e-9)
        return str(a) == str(b)

    checks = {
        "set_readback": same(after, expected),
        "restored": same(restored, before),
        "changed": not same(before, after),
    }
    detail = {"name": name, "expected": expected, "before": before,
              "after": after, "restored": restored}
    return verdict(checks, detail, dict(recorded))


def judge_dimstyle(rb: Readback, *, name: str, height: float,
                  reopen: bool = True) -> Dict[str, Any]:
    tables = rb.memory.meta.get("tables") or {}
    vars_ = rb.memory.meta.get("vars") or {}
    re_tables = ((rb.reopened.meta.get("tables") or {})
                 if rb.reopened else {})
    re_vars = ((rb.reopened.meta.get("vars") or {}) if rb.reopened else {})
    checks = {
        "style_row": name in (tables.get("dimstyles") or {}),
        "active": tables.get("active_dimstyle") == name,
        "dimtxt": close(vars_.get("DIMTXT"), height, 1e-9),
    }
    if reopen:
        checks["reopen"] = bool(re_tables.get("active_dimstyle") == name
                                and close(re_vars.get("DIMTXT"), height, 1e-9))
    detail = {"name": name, "height": height,
              "active_read": tables.get("active_dimstyle"),
              "dimtxt_read": vars_.get("DIMTXT"),
              "active_reopened": re_tables.get("active_dimstyle"),
              "dimtxt_reopened": re_vars.get("DIMTXT")}
    return verdict(checks, detail, {"tables": tables, "vars": vars_})
