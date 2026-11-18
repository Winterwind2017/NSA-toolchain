"""图层类 builder：建层 / 设当前层 / 图层状态保存与恢复。"""

from __future__ import annotations

import os
from typing import Any, Dict

from ..core import com
from .helpers import add, ms_of, pt, send


def _trace(msg: str) -> None:
    """`ACADKIT_DEBUG=1` 时打印步骤（命令卡死时用它定位停在哪一步）。"""
    if os.environ.get("ACADKIT_DEBUG"):
        print("[layer] " + msg, flush=True)


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def _ensure_layer(doc: Any, name: str, color: int = 3):
    layers = com.retry(lambda: doc.Layers, label="Layers")
    try:
        return layers.Item(name)
    except Exception:                               # noqa: BLE001
        lay = com.retry(lambda: layers.Add(name), label="Layers.Add")
        lay.Color = int(color)
        return lay


def build_layer_create(doc: Any, ctx: Dict[str, Any]) -> None:
    name = str(_p(ctx, "name", "01_OUTLINE"))
    _ensure_layer(doc, name, int(_p(ctx, "color", 3)))


def build_layer_set_current(doc: Any, ctx: Dict[str, Any]) -> None:
    """建层 → 设为当前 → 在它上面画一个圆（证明"新实体落在这层"）。"""
    name = str(_p(ctx, "name", "02_CENTER"))
    _ensure_layer(doc, name, int(_p(ctx, "color", 4)))
    doc.ActiveLayer = com.retry(lambda: doc.Layers.Item(name), label="Layers.Item")
    ms = ms_of(doc)
    add(ms, "AddCircle", pt(0, 0, 0), 10.0, label="AddCircle")


# 图层状态（属性级快照）：AutoCAD 的命名图层状态（`-LAYERSTATE`）在 COM 下
# 只要动过图层表就**永久卡在命令提示符**（SaveAs 之后也一样），所以本内核
# 不提供命名图层状态，改为"属性级快照 → 改 → 恢复"，同样可判、可交付。
_SNAP_KEYS = ("Color", "Linetype", "Lineweight", "Freeze", "Lock", "LayerOn")


def _layer_rows(doc: Any) -> Dict[str, Dict[str, Any]]:
    layers = com.retry(lambda: doc.Layers, label="Layers")
    rows: Dict[str, Dict[str, Any]] = {}
    for i in range(int(layers.Count)):
        lay = com.retry(lambda i=i: layers.Item(i), label="Layers.Item")
        name = str(lay.Name)
        row = {}
        for key in _SNAP_KEYS:
            try:
                val = getattr(lay, key)
            except Exception:                       # noqa: BLE001
                continue
            if isinstance(val, bool):
                row[key] = val
            else:
                try:
                    row[key] = int(val)
                except (TypeError, ValueError):
                    row[key] = str(val)
        rows[name] = row
    return rows


def build_layer_snapshot(doc: Any, ctx: Dict[str, Any]) -> None:
    """属性级图层状态：快照 → 改三处 → 恢复。"""
    name = str(_p(ctx, "name", "04_SNAP"))
    _ensure_layer(doc, name, 6)
    snap = _layer_rows(doc)
    mut: Dict[str, Dict[str, Any]] = {}
    try:
        lay = doc.Layers.Item(name)
        lay.Color = 1
        lay.Freeze = True
        mut[name] = {"Color": 1, "Freeze": True}
    except Exception as exc:                        # noqa: BLE001
        ctx["notes"].append("改层属性失败：%s: %s" % (type(exc).__name__, exc))
    try:
        zero = doc.Layers.Item("0")
        zero.Color = 4
        mut["0"] = {"Color": 4}
    except Exception as exc:                        # noqa: BLE001
        ctx["notes"].append("改 0 层失败：%s: %s" % (type(exc).__name__, exc))
    changed = _layer_rows(doc)
    for lname, props in snap.items():
        try:
            lay = doc.Layers.Item(lname)
        except Exception:                           # noqa: BLE001
            continue
        for key, val in props.items():
            try:
                setattr(lay, key, val)
            except Exception:                       # noqa: BLE001
                pass
    ctx.setdefault("artifacts", {})["snapshot"] = {
        "name": name, "snapshot": snap, "mutated": mut,
        "changed": changed, "restored": _layer_rows(doc),
    }

