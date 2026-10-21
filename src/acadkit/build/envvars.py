"""系统变量类 builder：普通变量 / 标注样式。"""

from __future__ import annotations

from typing import Any, Dict



def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def build_sysvar(doc: Any, ctx: Dict[str, Any]) -> None:
    """设一个文档级系统变量 → 读回 → 还原 → 再读回。"""
    name = str(_p(ctx, "name", "DIMTXT"))
    value = float(_p(ctx, "value", 3.5))
    before = doc.GetVariable(name)
    doc.SetVariable(name, value)
    after = doc.GetVariable(name)
    doc.SetVariable(name, before)
    restored = doc.GetVariable(name)
    ctx.setdefault("artifacts", {})["sysvar"] = {
        "name": name, "value": value, "before": before,
        "after": after, "restored": restored,
    }
