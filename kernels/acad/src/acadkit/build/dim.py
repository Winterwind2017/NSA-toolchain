"""标注类 builder：线性 / 对齐 / 直径 / 半径 / 角度 / 坐标 / 弧长 /
基线 / 连续 / 公差 / 配合代号（纯 Python）。
"""

from __future__ import annotations

from typing import Any, Dict

from ..fit import fit_deviation
from .helpers import add, ms_of, pt


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def build_linear(doc: Any, ctx: Dict[str, Any]) -> None:
    p1 = _p(ctx, "p1", (0.0, 0.0, 0.0))
    p2 = _p(ctx, "p2", (60.0, 0.0, 0.0))
    dim_line = _p(ctx, "dim_line", (30.0, 10.0, 0.0))
    ms = ms_of(doc)
    add(ms, "AddLine", pt(*p1), pt(*p2), label="AddLine")
    add(ms, "AddDimRotated", pt(*p1), pt(*p2), pt(*dim_line), 0.0,
        label="AddDimRotated")


def build_aligned(doc: Any, ctx: Dict[str, Any]) -> None:
    p1 = _p(ctx, "p1", (200.0, 0.0, 0.0))
    p2 = _p(ctx, "p2", (260.0, 0.0, 0.0))
    pos = _p(ctx, "text_pos", (230.0, 10.0, 0.0))
    ms = ms_of(doc)
    add(ms, "AddDimAligned", pt(*p1), pt(*p2), pt(*pos), label="AddDimAligned")


def build_diametric(doc: Any, ctx: Dict[str, Any]) -> None:
    radius = float(_p(ctx, "radius", 25.0))
    cx, cy, _ = _p(ctx, "center", (10.0, 20.0, 0.0))
    ms = ms_of(doc)
    add(ms, "AddCircle", pt(cx, cy, 0.0), radius, label="AddCircle")
    add(ms, "AddDimDiametric", pt(cx + radius, cy, 0.0),
        pt(cx - radius, cy, 0.0), 8.0, label="AddDimDiametric")


def build_radial(doc: Any, ctx: Dict[str, Any]) -> None:
    radius = float(_p(ctx, "radius", 25.0))
    cx, cy, _ = _p(ctx, "center", (10.0, 20.0, 0.0))
    ms = ms_of(doc)
    add(ms, "AddCircle", pt(cx, cy, 0.0), radius, label="AddCircle")
    add(ms, "AddDimRadial", pt(cx, cy, 0.0), pt(cx + radius, cy, 0.0), 8.0,
        label="AddDimRadial")


def build_angular(doc: Any, ctx: Dict[str, Any]) -> None:
    vertex = _p(ctx, "vertex", (300.0, 0.0, 0.0))
    p1 = _p(ctx, "p1", (320.0, 0.0, 0.0))
    p2 = _p(ctx, "p2", (300.0, 20.0, 0.0))
    pos = _p(ctx, "text_pos", (310.0, 10.0, 0.0))
    ms = ms_of(doc)
    add(ms, "AddDimAngular", pt(*vertex), pt(*p1), pt(*p2), pt(*pos),
        label="AddDimAngular")


def build_ordinate(doc: Any, ctx: Dict[str, Any]) -> None:
    point = _p(ctx, "point", (350.0, 0.0, 0.0))
    leader = _p(ctx, "leader", (360.0, 10.0, 0.0))
    ms = ms_of(doc)
    add(ms, "AddDimOrdinate", pt(*point), pt(*leader), bool(_p(ctx, "use_x", True)),
        label="AddDimOrdinate")


def build_arc_dim(doc: Any, ctx: Dict[str, Any]) -> None:
    center = _p(ctx, "center", (400.0, 0.0, 0.0))
    start = _p(ctx, "start", (420.0, 0.0, 0.0))
    end = _p(ctx, "end", (400.0, 20.0, 0.0))
    pos = _p(ctx, "text_pos", (412.0, 12.0, 0.0))
    ms = ms_of(doc)
    add(ms, "AddDimArc", pt(*center), pt(*start), pt(*end), pt(*pos),
        label="AddDimArc")


def build_baseline(doc: Any, ctx: Dict[str, Any]) -> None:
    """基线标注：同一条尺寸线上的两段（共享基线）。"""
    ms = ms_of(doc)
    add(ms, "AddLine", pt(0, 0, 0), pt(100, 0, 0), label="AddLine")
    add(ms, "AddDimRotated", pt(0, 0, 0), pt(40, 0, 0), pt(20, 10, 0), 0.0,
        label="AddDimRotated")
    add(ms, "AddDimRotated", pt(0, 0, 0), pt(100, 0, 0), pt(50, 20, 0), 0.0,
        label="AddDimRotated")


def build_continuous(doc: Any, ctx: Dict[str, Any]) -> None:
    """连续标注：相邻两段首尾相接，两段之和 = 总长。"""
    ms = ms_of(doc)
    add(ms, "AddLine", pt(0, 0, 0), pt(100, 0, 0), label="AddLine")
    add(ms, "AddDimRotated", pt(0, 0, 0), pt(40, 0, 0), pt(20, 10, 0), 0.0,
        label="AddDimRotated")
    add(ms, "AddDimRotated", pt(40, 0, 0), pt(100, 0, 0), pt(70, 10, 0), 0.0,
        label="AddDimRotated")


def build_tolerance(doc: Any, ctx: Dict[str, Any]) -> None:
    """尺寸公差：DIMTOL/DIMTP/DIMTM + TextOverride。

    本机 ActiveX 的标注没有 Tolerance 字段（spec 2.3 允许走 TextOverride 读回）。
    """
    ms = ms_of(doc)
    dim = add(ms, "AddDimRotated", pt(0, 0, 0), pt(60, 0, 0), pt(30, 10, 0), 0.0,
              label="AddDimRotated")
    upper = float(_p(ctx, "upper", 0.02))
    lower = float(_p(ctx, "lower", 0.01))
    doc.SetVariable("DIMTOL", 1)
    doc.SetVariable("DIMTP", upper)
    doc.SetVariable("DIMTM", lower)
    dim.TextOverride = str(_p(ctx, "override", "60 +0.02/-0.01"))
    ctx.setdefault("artifacts", {})["tolerance"] = {
        "DIMTOL": int(doc.GetVariable("DIMTOL")),
        "DIMTP": float(doc.GetVariable("DIMTP")),
        "DIMTM": float(doc.GetVariable("DIMTM")),
        "text_override": str(dim.TextOverride),
    }


def build_fit_code(doc: Any, ctx: Dict[str, Any]) -> None:
    """纯 Python：查 GB/T 1800 配合表（不碰 AutoCAD）。"""
    ctx.setdefault("artifacts", {})
    code = str(_p(ctx, "code", "H7"))
    nominal = float(_p(ctx, "nominal", 50.0))
    upper, lower = fit_deviation(code, nominal)
    ctx["artifacts"]["fit"] = {"code": code, "nominal": nominal,
                               "upper_mm": upper, "lower_mm": lower}


def build_missing_api(doc: Any, ctx: Dict[str, Any]) -> None:
    """负例：`AddDimLinear` 在本机不存在，调用必须抛错。"""
    ms = ms_of(doc)
    try:
        ms.AddDimLinear(pt(0, 0, 0), pt(60, 0, 0), pt(30, -10, 0))
        ctx["artifacts"]["raised"] = None
        ctx["notes"].append("AddDimLinear 竟然调用成功——负例前提不成立")
    except Exception as exc:                        # noqa: BLE001
        ctx["artifacts"]["raised"] = type(exc).__name__
        ctx["notes"].append("AddDimLinear -> %s" % type(exc).__name__)


def build_dimstyle(doc: Any, ctx: Dict[str, Any]) -> None:
    """标注样式：ActiveDimStyle 设为当前 + (setvar "DIMTXT" …)。

    本机实测：其它写法（直接改 DimStyle 记录）都会失败，只有"设为当前 + setvar"有效。
    """
    name = str(_p(ctx, "name", "ACADKIT_DIM"))
    height = float(_p(ctx, "dimtxt", 3.5))
    styles = doc.DimStyles
    try:
        styles.Item(name)
    except Exception:                               # noqa: BLE001
        styles.Add(name)
    doc.ActiveDimStyle = styles.Item(name)
    doc.SetVariable("DIMTXT", height)
    ctx.setdefault("artifacts", {})["dimstyle"] = {
        "name": str(doc.ActiveDimStyle.Name),
        "dimtxt": float(doc.GetVariable("DIMTXT")),
    }


def update_rotated(doc: Any, old_dim: Any, p1, p2, dim_line,
                   rotation: float = 0.0) -> Dict[str, Any]:
    """非关联标注的"重建式更新"（`dim.update` 的实现）。

    为什么是重建而不是改定义点：本机实测（2026-11-18）
    `AcadDimension.ExtLine1Point / ExtLine2Point / DimLineLocation` **只读**
    —— 读抛 AttributeError，写报 "Property ... can not be set"，命令行 DIMUPDATE
    也不存在。所以"更新"只能是：读旧值 → 删旧 → 按新定义点重建同类型标注 →
    把样式抄回去。

    返回旧值/新值的对照，供判据核对（判据不读返回值当结论，读的是重建后的读回）。
    """
    style = str(old_dim.StyleName)
    old_meas = float(old_dim.Measurement)
    old_handle = str(old_dim.Handle)
    old_rot = float(old_dim.Rotation)
    old_dim.Delete()
    ms = ms_of(doc)
    new = add(ms, "AddDimRotated", pt(*p1), pt(*p2), pt(*dim_line), float(rotation),
              label="AddDimRotated(update)")
    try:
        new.StyleName = style
    except Exception:                               # noqa: BLE001
        pass
    return {
        "old_handle": old_handle,
        "old_measurement": old_meas,
        "old_rotation": old_rot,
        "old_style": style,
        "new_handle": str(new.Handle),
        "new_measurement": float(new.Measurement),
        "new_style": str(new.StyleName),
        "new_rotation": float(new.Rotation),
    }


def build_update(doc: Any, ctx: Dict[str, Any]) -> None:
    """先建一条 40 的旧标注，再按新定义点重建为 60（模拟"改图后刷新标注"）。"""
    p1 = _p(ctx, "p1", (0.0, 0.0, 0.0))
    p2 = _p(ctx, "p2", (40.0, 0.0, 0.0))
    dim_line = _p(ctx, "dim_line", (20.0, 10.0, 0.0))
    p1_new = _p(ctx, "p1_new", (0.0, 0.0, 0.0))
    p2_new = _p(ctx, "p2_new", (60.0, 0.0, 0.0))
    dim_line_new = _p(ctx, "dim_line_new", (30.0, 10.0, 0.0))
    ms = ms_of(doc)
    old = add(ms, "AddDimRotated", pt(*p1), pt(*p2), pt(*dim_line), 0.0,
              label="AddDimRotated(before update)")
    info = update_rotated(doc, old, p1_new, p2_new, dim_line_new, 0.0)
    ctx.setdefault("artifacts", {})["update"] = info
