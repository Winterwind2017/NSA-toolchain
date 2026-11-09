"""三视图判据：独立重算投影 → 逐层点数 + 包围尺寸 + 重开一致。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import csg
from ..build.projection import LAYER_AXIS, LAYER_HIDDEN, LAYER_VISIBLE
from .base import Readback, verdict


def _counts(drawing, layers: Dict[str, str]) -> Dict[str, int]:
    out = {name: 0 for name in layers}
    for e in drawing.entities:
        lay = str(e.attrs.get("Layer") or "")
        for name, layer in layers.items():
            if lay == layer:
                out[name] += 1
    return out


def judge_projection(rb: Readback, *,
                     recorded: Dict[str, Any]) -> Dict[str, Any]:
    model = recorded.get("model") or []
    views = recorded.get("views") or {}
    # 独立重算（不信任 builder 的记录）
    expected: Dict[str, Dict[str, int]] = {}
    for view in ("front", "top", "left"):
        prims = csg.project(model, view)
        hidden = sum(1 for p in prims if p.get("hidden"))
        axis = sum(1 for p in prims if p.get("src") == "axis")
        visible = len(prims) - hidden - axis
        expected[view] = {"visible": visible, "hidden": hidden, "axis": axis}

    got = _counts(rb.memory, {"visible": LAYER_VISIBLE,
                              "hidden": LAYER_HIDDEN,
                              "axis": LAYER_AXIS})
    exp_total = {k: sum(v[k] for v in expected.values())
                 for k in ("visible", "hidden", "axis")}
    sizes = recorded.get("sizes") or {}
    reopen_same = True
    if rb.reopened is not None:
        got_re = _counts(rb.reopened, {"visible": LAYER_VISIBLE,
                                       "hidden": LAYER_HIDDEN,
                                       "axis": LAYER_AXIS})
        reopen_same = got_re == got

    def near(a: Optional[float], b: float, tol: float = 0.5) -> bool:
        return a is not None and abs(float(a) - b) <= tol

    checks = {
        "visible_count": got["visible"] == exp_total["visible"],
        "hidden_count": got["hidden"] == exp_total["hidden"],
        "axis_count": got["axis"] == exp_total["axis"],
        "front_size": near((sizes.get("front") or [None])[0], 100.0)
        and near((sizes.get("front") or [None, None])[1], 30.0),
        "top_size": near((sizes.get("top") or [None])[0], 100.0)
        and near((sizes.get("top") or [None, None])[1], 60.0),
        "left_size": near((sizes.get("left") or [None])[0], 60.0)
        and near((sizes.get("left") or [None, None])[1], 30.0),
        "reopen": reopen_same,
    }
    detail = {
        "expected": expected,
        "expected_total": exp_total,
        "drawn": got,
        "sizes": sizes,
        "views": {k: v.get("counts") for k, v in views.items()},
        "hidden_linetype": recorded.get("hidden_linetype"),
        "reopen_counts": (_counts(rb.reopened, {"visible": LAYER_VISIBLE,
                                                "hidden": LAYER_HIDDEN,
                                                "axis": LAYER_AXIS})
                          if rb.reopened is not None else None),
    }
    raw = {"recorded": recorded, "drawn": got}
    return verdict(checks, detail, raw)
