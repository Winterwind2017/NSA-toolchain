"""三视图投影 builder：CSG 模型 → front/top/left 三视图（可见/隐藏/轴线分层）。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .. import csg
from ..core import com
from .helpers import add, dbl, ms_of, pt

LAYER_VISIBLE = "PROJ_VISIBLE"
LAYER_HIDDEN = "PROJ_HIDDEN"
LAYER_AXIS = "PROJ_AXIS"

# 测试模型：100×60×20 底板 + Ø32×10 凸台 + Ø20 通孔（沿 Z）
MODEL: List[Dict[str, Any]] = [
    {"type": "box", "x": [0, 100], "y": [0, 60], "z": [0, 20]},
    {"type": "cyl", "axis": "z", "c": [50, 30], "a": [0, 20], "r": 10, "op": "sub"},
    {"type": "cyl", "axis": "z", "c": [50, 30], "a": [20, 30], "r": 16},
]

# 视图在图纸上的偏移（三视图标准布置：主视左下、俯视在上、左视在右）
OFFSETS: Dict[str, Tuple[float, float]] = {
    "front": (0.0, 0.0),
    "top": (0.0, 90.0),
    "left": (140.0, 0.0),
}


def _ensure_layer(doc: Any, name: str, color: int) -> Any:
    layers = com.retry(lambda: doc.Layers, label="Layers")
    try:
        return layers.Item(name)
    except Exception:                               # noqa: BLE001
        lay = com.retry(lambda: layers.Add(name), label="Layers.Add")
        try:
            lay.Color = color
        except Exception:                           # noqa: BLE001
            pass
        return lay


def _hidden_linetype(doc: Any) -> str:
    """尽量给隐藏线挂 HIDDEN 线型；挂不上就用分层来区分（判据只看层）。"""
    try:
        lts = com.retry(lambda: doc.Linetypes, label="Linetypes")
        try:
            lts.Item("HIDDEN")
        except Exception:                           # noqa: BLE001
            lts.Load("HIDDEN", "acadiso.lin")
        return "HIDDEN"
    except Exception:                               # noqa: BLE001
        return "Continuous"


def build_projection(doc: Any, ctx: Dict[str, Any]) -> None:
    model = (ctx.get("params") or {}).get("model") or MODEL
    _ensure_layer(doc, LAYER_VISIBLE, 7)
    _ensure_layer(doc, LAYER_HIDDEN, 8)
    _ensure_layer(doc, LAYER_AXIS, 1)
    hidden_lt = _hidden_linetype(doc)
    ms = ms_of(doc)
    drawn: Dict[str, Any] = {}
    for view, (ox, oy) in OFFSETS.items():
        prims = csg.project(model, view)
        n = {"seg": 0, "circle": 0, "hidden": 0, "axis": 0}
        for p in prims:
            if p["kind"] == "circle":
                c = p["c"]
                circle = add(ms, "AddCircle", pt(ox + c[0], oy + c[1], 0),
                             float(p["r"]), label="AddCircle")
                circle.Layer = LAYER_HIDDEN if p.get("hidden") else LAYER_VISIBLE
                n["circle"] += 1
            else:
                line = add(ms, "AddLine",
                           pt(ox + p["p"][0], oy + p["p"][1], 0),
                           pt(ox + p["q"][0], oy + p["q"][1], 0),
                           label="AddLine")
                if p.get("src") == "axis":
                    line.Layer = LAYER_AXIS
                    n["axis"] += 1
                elif p.get("hidden"):
                    line.Layer = LAYER_HIDDEN
                    n["hidden"] += 1
                    try:
                        line.Linetype = hidden_lt
                    except Exception:               # noqa: BLE001
                        pass
                else:
                    line.Layer = LAYER_VISIBLE
                n["seg"] += 1
        drawn[view] = {"offset": [ox, oy], "counts": n,
                       "expected": csg.summary(prims)}
    # 三视图的包围尺寸（判据用：主视 100×20、俯视 100×60、左视 60×20）
    sizes = {}
    for view in OFFSETS:
        prims = csg.project(model, view)
        xs = [v for p in prims for v in ((p["p"][0], p["q"][0]) if p["kind"] == "seg"
                                         else (p["c"][0] - p["r"], p["c"][0] + p["r"]))]
        ys = [v for p in prims for v in ((p["p"][1], p["q"][1]) if p["kind"] == "seg"
                                         else (p["c"][1] - p["r"], p["c"][1] + p["r"]))]
        sizes[view] = [round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)]
    ctx["artifacts"]["projection"] = {
        "model": model, "views": drawn, "sizes": sizes,
        "hidden_linetype": hidden_lt,
    }
