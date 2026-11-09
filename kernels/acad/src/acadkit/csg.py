"""轴对齐 CSG 的正交投影（三视图）—— 纯 Python，不依赖 AutoCAD。

本机实测（`docs/UNSUPPORTED.md`）：AutoCAD 2025 **没有任何官方 3D→2D 出图命令**
（SOLVIEW/SOLDRAW/SOLPROF/VIEWBASE/SECTION/FLATSHOT/EXPORTLAYOUT 全缺），所以
投影必须自建。这里只处理轴对齐的 `box` 与 `cyl`（机械零件最常见），做严格正交
投影 + 简单隐藏线判定。

实体写法（dict）：

    {"type": "box", "x": [x1, x2], "y": [y1, y2], "z": [z1, z2], "op": "add"}
    {"type": "cyl", "axis": "z", "c": [cx, cy], "a": [a1, a2], "r": 10,
     "op": "sub"}

视图：`front`（沿 −Y 看，u=X v=Z）、`top`（沿 −Z 看，u=X v=Y）、
`left`（沿 +X 看，u=Y v=Z）。

返回图元：

    {"kind": "seg", "p": (u1, v1), "q": (u2, v2), "hidden": bool, "src": ...}
    {"kind": "circle", "c": (cu, cv), "r": r, "hidden": bool, "src": ...}
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# view: (u_axis, v_axis, depth_axis, 近端方向)
VIEW_AXES: Dict[str, Tuple[int, int, int, int]] = {
    "front": (0, 2, 1, +1),
    "top": (0, 1, 2, +1),
    "left": (1, 2, 0, +1),
    "right": (1, 2, 0, -1),
}


def _box(s: Dict[str, Any]) -> Tuple[float, float, float, float, float, float]:
    def rng(key: str, key2: str) -> Tuple[float, float]:
        val = s.get(key)
        if isinstance(val, (list, tuple)):
            return float(val[0]), float(val[1])
        if val is None:
            raise ValueError("box 缺少 %r" % key)
        return float(val), float(s[key2])
    x1, x2 = rng("x", "x2")
    y1, y2 = rng("y", "y2")
    z1, z2 = rng("z", "z2")
    return (min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2),
            min(z1, z2), max(z1, z2))


def _cyl(s: Dict[str, Any]) -> Tuple[int, float, float, float, float, float]:
    idx = {"x": 0, "y": 1, "z": 2}[str(s.get("axis", "z")).lower()]
    c = s.get("c") or s.get("center") or [0, 0]
    c1, c2 = float(c[0]), float(c[1])
    a = s.get("a") or s.get("range")
    if a is None:
        a1, a2 = float(s.get("a1", 0)), float(s.get("a2", 0))
    elif isinstance(a, (list, tuple)):
        a1, a2 = float(a[0]), float(a[1])
    else:
        a1, a2 = float(a), float(s.get("a2", a))
    return idx, c1, c2, min(a1, a2), max(a1, a2), float(s.get("r", s.get("radius", 0)))


def bbox(s: Dict[str, Any]) -> Tuple[float, ...]:
    if str(s.get("type", "")).lower() == "box":
        return _box(s)
    idx, c1, c2, a1, a2, r = _cyl(s)
    lo = [0.0, 0.0, 0.0]
    hi = [0.0, 0.0, 0.0]
    lo[idx], hi[idx] = a1, a2
    o1, o2 = [i for i in (0, 1, 2) if i != idx]
    lo[o1], hi[o1] = c1 - r, c1 + r
    lo[o2], hi[o2] = c2 - r, c2 + r
    return (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])


def footprint(bb: Sequence[float], view: str) -> Tuple[float, float, float, float, float, float]:
    u, v, d, _ = VIEW_AXES[view]
    lo = (bb[0], bb[2], bb[4])
    hi = (bb[1], bb[3], bb[5])
    return (lo[u], hi[u], lo[v], hi[v], lo[d], hi[d])


def _inside(fp: Sequence[float], pt: Tuple[float, float], tol: float = 1e-9) -> bool:
    return (fp[0] - tol <= pt[0] <= fp[1] + tol
            and fp[2] - tol <= pt[1] <= fp[3] + tol)


def _cyl_uv(idx: int, c1: float, c2: float, u: int, v: int) -> Tuple[float, float]:
    others = [i for i in (0, 1, 2) if i != idx]
    m = {others[0]: c1, others[1]: c2}
    return (m.get(u, c1), m.get(v, c2))


def project(solids: List[Dict[str, Any]], view: str) -> List[Dict[str, Any]]:
    """把 CSG 实体投影到视图平面，返回线段/圆（含 hidden 标记）。"""
    v = VIEW_AXES[view]
    u, v_ax, d, dsign = v

    adds, subs = [], []
    for s in solids:
        bb = bbox(s)
        rec = {"bb": bb, "fp": footprint(bb, view),
               "type": str(s.get("type", "")).lower(), "s": s}
        (subs if str(s.get("op", "add")).lower() == "sub" else adds).append(rec)

    out: List[Dict[str, Any]] = []

    def depth_near(fp: Sequence[float]) -> float:
        return fp[5] if dsign > 0 else -fp[4]

    def hidden_at(pt: Tuple[float, float], own: Dict[str, Any]) -> bool:
        own_near = depth_near(own["fp"])
        for a in adds:
            if a is own:
                continue
            if depth_near(a["fp"]) > own_near + 1e-9 and _inside(a["fp"], pt):
                return True
        return False

    for rec in adds:
        fp = rec["fp"]
        u1, u2, v1, v2 = fp[0], fp[1], fp[2], fp[3]
        is_cyl = rec["type"] in ("cyl", "cylinder", "circle")
        if is_cyl:
            idx, c1, c2, a1, a2, r = _cyl(rec["s"])
            if idx == d:
                cu, cv = _cyl_uv(idx, c1, c2, u, v_ax)
                out.append({"kind": "circle", "c": (cu, cv), "r": r,
                            "hidden": hidden_at((cu, cv), rec), "src": "add"})
                continue
        for p, q in (((u1, v1), (u2, v1)), ((u2, v1), (u2, v2)),
                     ((u2, v2), (u1, v2)), ((u1, v2), (u1, v1))):
            out.append({"kind": "seg", "p": p, "q": q,
                        "hidden": hidden_at(((p[0] + q[0]) / 2.0,
                                             (p[1] + q[1]) / 2.0), rec),
                        "src": "add"})
        if is_cyl:
            idx, c1, c2, a1, a2, r = _cyl(rec["s"])
            cu, cv = _cyl_uv(idx, c1, c2, u, v_ax)
            others = [i for i in (0, 1, 2) if i != idx]
            if u in others:
                out.append({"kind": "seg", "p": (a1, cv), "q": (a2, cv),
                            "hidden": False, "src": "axis"})
            else:
                out.append({"kind": "seg", "p": (cu, a1), "q": (cu, a2),
                            "hidden": False, "src": "axis"})

    for rec in subs:
        fp = rec["fp"]
        if rec["type"] in ("cyl", "cylinder", "circle"):
            idx, c1, c2, a1, a2, r = _cyl(rec["s"])
            cu, cv = _cyl_uv(idx, c1, c2, u, v_ax)
            if idx == d:
                out.append({"kind": "circle", "c": (cu, cv), "r": r,
                            "hidden": False, "src": "hole"})
            elif idx == u:
                out.append({"kind": "seg", "p": (a1, fp[3]), "q": (a2, fp[3]),
                            "hidden": True, "src": "hole"})
                out.append({"kind": "seg", "p": (a1, fp[2]), "q": (a2, fp[2]),
                            "hidden": True, "src": "hole"})
            else:
                out.append({"kind": "seg", "p": (fp[1], a1), "q": (fp[1], a2),
                            "hidden": True, "src": "hole"})
                out.append({"kind": "seg", "p": (fp[0], a1), "q": (fp[0], a2),
                            "hidden": True, "src": "hole"})
        else:
            u1, u2, v1, v2 = fp[0], fp[1], fp[2], fp[3]
            for p, q in (((u1, v1), (u2, v1)), ((u2, v1), (u2, v2)),
                         ((u2, v2), (u1, v2)), ((u1, v2), (u1, v1))):
                out.append({"kind": "seg", "p": p, "q": q,
                            "hidden": True, "src": "hole"})
    return out


def summary(prims: List[Dict[str, Any]]) -> Dict[str, int]:
    """按 类型/可见性/来源 计数（判据用）。"""
    out: Dict[str, int] = {}
    for p in prims:
        key = "%s/%s/%s" % (p["kind"], "hidden" if p.get("hidden") else "visible",
                            p.get("src", "add"))
        out[key] = out.get(key, 0) + 1
    return out
