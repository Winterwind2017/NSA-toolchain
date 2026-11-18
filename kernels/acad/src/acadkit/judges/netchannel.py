"""`solid.revolve` / `layer.state` 的判据（走 .NET 通道）。

这两条的证据由插件写在图面 MText（`AKRESULT <tag>: ...`）里，判据把它读出来，
但**不以它为准**：

* `solid.revolve`：真正的判据是读回里的 `3DSOLID.Volume` 是否等于
  π(R²−r²)h —— 与插件自述无关，几何错就是错。
* `layer.state`：读回的**图层颜色**（COM 侧真值）必须等于插件声称恢复到的值；
  插件若谎称"恢复了"，颜色会停在改后的值上，这条就会失败。
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional

from .base import Readback, close, num, reopen_check, verdict

MARK = "AKRESULT"


def results(rb: Readback, source: str = "memory") -> Dict[str, str]:
    """从某次读回里抽 `AKRESULT <tag>: <text>`。"""
    drawing = getattr(rb, source, None) or rb.memory
    out: Dict[str, str] = {}
    for ent in drawing.of_type("MTEXT") + drawing.of_type("TEXT"):
        text = str(ent.get("TextString") or "")
        m = re.match(r"%s\s+([A-Z_]+):\s*(.*)" % MARK, text, re.S)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _one_solid(rb: Readback) -> Optional[Any]:
    solids = rb.memory.of_type("3DSOLID")
    return solids[0] if len(solids) == 1 else None


def judge_revolve(rb: Readback, *, outer_r: float = 25.0, inner_r: float = 5.0,
                  height: float = 10.0, tol_rel: float = 0.01) -> Dict[str, Any]:
    """旋转体：恰好一个 3DSOLID，体积 = π(R²−r²)h（相对误差 ≤ tol_rel）。"""
    ent = _one_solid(rb)
    vol = num(ent.get("Volume")) if ent else None
    expected = math.pi * (outer_r ** 2 - inner_r ** 2) * height
    rel = (abs(vol - expected) / expected) if (vol is not None and expected) else None
    res = results(rb)
    claimed = res.get("REVOLVE", "")
    claimed_ratio = None
    m = re.search(r"ratio=([\d.]+)", claimed)
    if m:
        claimed_ratio = float(m.group(1))
    re_ok, re_detail = (reopen_check(rb, ent, ("Volume",))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到 3DSOLID"}}))
    checks = {
        "one_solid": ent is not None,
        "volume": rel is not None and rel <= tol_rel,
        "plugin_ran": "volume=" in claimed,
        "reopen": re_ok,
    }
    detail: Dict[str, Any] = {
        "handle": ent.handle if ent else None,
        "volume_mm3": vol,
        "volume_expected_mm3": round(expected, 3),
        "volume_rel_error": (round(rel, 6) if rel is not None else None),
        "plugin_claim": claimed or None,
        "plugin_claim_ratio": claimed_ratio,
        "formula": "pi*(R^2-r^2)*h = pi*(%g^2-%g^2)*%g" % (outer_r, inner_r, height),
        "reopen": re_detail,
        "channel": "dotnet (AcadKit.Plugin ACADKITREVOLVE)",
    }
    return verdict(checks, detail, {"akresult": res})


def judge_layer_state(rb: Readback, *, layer_name: str = "AK_LS_A") -> Dict[str, Any]:
    """图层状态：插件自述 restored=1 且**读回颜色**确实回到原值。"""
    res = results(rb)
    claimed = res.get("LAYERSTATE", "")
    fields = dict(re.findall(r"(\w+)=([^\s]+)", claimed))
    before = fields.get("before")
    changed = fields.get("changed")
    after = fields.get("after")

    tables = (rb.memory.meta.get("tables") or {})
    layers = (tables.get("layers") or {}) if isinstance(tables, dict) else {}
    rec = layers.get(layer_name) or {}
    color = rec.get("Color") if isinstance(rec, dict) else None
    color_s = None
    if color is not None:
        color_s = str(getattr(color, "ColorIndex", color))

    checks = {
        "plugin_ran": "restored=" in claimed,
        "state_saved": str(fields.get("states", "0")) not in ("", "0"),
        "color_changed": bool(before and changed and before != changed),
        "restored_claim": fields.get("restored") == "1",
        # 交叉校验：COM 侧读到的图层颜色应当就是插件声称恢复到的颜色
        "color_back": bool(color_s and before and color_s.split(".")[-1] == str(before)),
    }
    detail: Dict[str, Any] = {
        "plugin_claim": claimed or None,
        "fields": fields,
        "layer": layer_name,
        "color_readback": color_s,
        "color_expected_after_restore": before,
        "color_while_changed": changed,
        "layers_seen": sorted(layers)[:12] if isinstance(layers, dict) else [],
        "channel": "dotnet (AcadKit.Plugin ACADKITLAYERSTATE)",
    }
    return verdict(checks, detail, {"akresult": res})
