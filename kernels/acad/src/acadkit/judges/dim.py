"""标注判据（JUDGE_SPEC 2.2）。

标注意义上的"做对了"必须读 `Measurement`，不能读返回值 —— `AddDimRotated`
返回对象不等于尺寸对。L4 对标注尤其重要：`DIMASSOC=2` 时 Measurement 由关联
几何决定，落盘/重开是唯一能证明关联没断的办法。

本机实测（2026-10-21）：
* `AddDimRotated` → `AcDbRotatedDimension`，`Measurement` = 60.0（精确）；
* 文字位置会被自动上移（y=10 传入 → 读回 11.875），所以"文字在预期侧"只能
  判方向，不能判相等；
* `AddDimLinear` 不存在（AttributeError）—— 负面对照用它。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from .base import (Entity, Readback, close, new_entities, num, pt3, reopen_check,
                   verdict)


def _new_one(rb: Readback, type_name: str) -> Optional[Entity]:
    new = new_entities(rb, type_name)
    return new[0] if len(new) == 1 else None


def _count_ok(rb: Readback, type_name: str) -> bool:
    return (rb.memory.count(type_name) == rb.before.count(type_name) + 1
            and len(new_entities(rb, type_name)) == 1)


def _text_side(text_pos: Optional[Tuple[float, float, float]],
               p1: Sequence[float], p2: Sequence[float],
               dim_line: Sequence[float]) -> Optional[bool]:
    """文字是否落在尺寸线的**外侧**（在 AutoCAD 自动上移文字后仍成立）。

    本机实测：传 (30, 10) 的 TextPosition，读回是 (30, 11.875) —— AutoCAD 会
    按文字高度自动偏移。所以判"方向"而不是判"相等"。
    """
    if text_pos is None:
        return None
    dx = float(p2[0]) - float(p1[0])
    dy = float(p2[1]) - float(p1[1])
    if abs(dx) >= abs(dy):                      # 水平标注：看 y 方向
        base = max(float(p1[1]), float(p2[1]))
        off = float(dim_line[1]) - base
        return ((text_pos[1] - float(dim_line[1])) * off > 0
                or (text_pos[1] - base) * off > 0)
    base = max(float(p1[0]), float(p2[0]))      # 垂直标注：看 x 方向
    off = float(dim_line[0]) - base
    return ((text_pos[0] - float(dim_line[0])) * off > 0
            or (text_pos[0] - base) * off > 0)


# ── 线性（水平 / 垂直）──────────────────────────────────────────────
def judge_linear(rb: Readback, *, p1=(0.0, 0.0), p2=(60.0, 0.0),
                 dim_line=(30.0, 10.0), expected: float = 60.0,
                 tol: float = 1e-6) -> Dict[str, Any]:
    ent = _new_one(rb, "ROTATEDDIMENSION")
    meas = num(ent.get("Measurement")) if ent else None
    text_pos = pt3(ent.get("TextPosition")) if ent else None
    side = _text_side(text_pos, p1, p2, dim_line) if ent else None
    re_ok, re_detail = (reopen_check(rb, ent, ("Measurement", "TextPosition"))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到新标注"}}))
    checks = {
        "count": _count_ok(rb, "ROTATEDDIMENSION"),
        "type": bool(ent) and ent.get("ObjectName") == "AcDbRotatedDimension",
        "measurement": close(meas, expected, tol),
        "text_side": side is True,
        "reopen": re_ok,
    }
    detail: Dict[str, Any] = {
        "handle": ent.handle if ent else None,
        "measurement_du": meas,
        "measurement_expected_du": float(expected),
        "measurement_mm": _mm(meas, rb),
        "text_position_du": text_pos,
        "dim_line_du": [float(dim_line[0]), float(dim_line[1])],
        "text_outside": side,
        "reopen": re_detail,
        "unit_note": "INSUNITS=%s" % rb.memory.insunits,
    }
    raw = {"before_counts": rb.before.counts, "memory_counts": rb.memory.counts,
           "entity": ent.attrs if ent else None}
    return verdict(checks, detail, raw)


# ── 直径 / 半径 ─────────────────────────────────────────────────────
def judge_diametric(rb: Readback, *, radius: float = 25.0,
                    tol: float = 1e-6) -> Dict[str, Any]:
    ent = _new_one(rb, "DIAMETRICDIMENSION")
    meas = num(ent.get("Measurement")) if ent else None
    expected = float(radius) * 2.0
    re_ok, re_detail = (reopen_check(rb, ent, ("Measurement",))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到直径标注"}}))
    checks = {
        "count": _count_ok(rb, "DIAMETRICDIMENSION"),
        "type": bool(ent) and ent.get("ObjectName") == "AcDbDiametricDimension",
        "measurement": close(meas, expected, tol),
        "reopen": re_ok,
    }
    detail: Dict[str, Any] = {
        "handle": ent.handle if ent else None,
        "measurement_du": meas,
        "measurement_expected_du": expected,
        "diameter_mm": _mm(meas, rb),
        "radius_source_du": float(radius),
        "reopen": re_detail,
    }
    raw = {"before_counts": rb.before.counts, "memory_counts": rb.memory.counts,
           "entity": ent.attrs if ent else None}
    return verdict(checks, detail, raw)


def judge_radial(rb: Readback, *, radius: float = 25.0,
                 tol: float = 1e-6) -> Dict[str, Any]:
    ent = _new_one(rb, "RADIALDIMENSION")
    meas = num(ent.get("Measurement")) if ent else None
    re_ok, re_detail = (reopen_check(rb, ent, ("Measurement",))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到半径标注"}}))
    checks = {
        "count": _count_ok(rb, "RADIALDIMENSION"),
        "type": bool(ent) and ent.get("ObjectName") == "AcDbRadialDimension",
        "measurement": close(meas, radius, tol),
        "reopen": re_ok,
    }
    detail: Dict[str, Any] = {
        "handle": ent.handle if ent else None,
        "measurement_du": meas,
        "measurement_expected_du": float(radius),
        "radius_mm": _mm(meas, rb),
        "reopen": re_detail,
    }
    raw = {"before_counts": rb.before.counts, "memory_counts": rb.memory.counts,
           "entity": ent.attrs if ent else None}
    return verdict(checks, detail, raw)


# ── 负面对照：不存在的 API 必须抛错 ─────────────────────────────────
def judge_raised(recorded: Optional[str], *,
                 expected: Sequence[str] = ("AttributeError",)) -> Dict[str, Any]:
    """把"调用抛了什么异常"变成判据。

    `docs/JUDGE_SPEC.md` 第四节：`dim.diametric` 的负例是"用 AddDimLinear
    （不存在）→ 调用直接报错"。能失败的判据才证明得了成功。
    """
    checks = {
        "raised": recorded is not None,
        "right_exception": recorded in set(expected),
    }
    detail = {"raised": recorded, "expected": list(expected)}
    return verdict(checks, detail, {"recorded": recorded})


def _mm(v: Optional[float], rb: Readback) -> Optional[float]:
    scale = rb.memory.unit_scale_mm
    if v is None or scale is None:
        return None
    return round(v * scale, 6)


def judge_update(rb: Readback, *, info: Dict[str, Any],
                 expected_old: float = 40.0, expected_new: float = 60.0,
                 tol: float = 1e-6) -> Dict[str, Any]:
    """`dim.update` 的判据：旧标注真的没了、新标注真的换了值、样式没丢、重开还在。

    注意这里**不用** `_count_ok`：重建是"删一个 + 加一个"，条数不变，
    数数区分不了"更新成功"和"什么都没做"。所以判 4 件更硬的事：
      1. 内存里恰好 1 条新标注；
      2. 旧 handle 已经查不到（真的删了，而不是叠了一条）；
      3. Measurement = 新值，且 != 旧值（证明确实改了，不是恰好相等）；
      4. 样式沿用旧标注的，重开后 Measurement/StyleName 一致。
    """
    ent = _new_one(rb, "ROTATEDDIMENSION")
    old_handle = str((info or {}).get("old_handle") or "")
    new_handle = str((info or {}).get("new_handle") or "")
    meas = num(ent.get("Measurement")) if ent else None
    style = str(ent.get("StyleName")) if ent else None
    want_style = str((info or {}).get("old_style") or "")
    old_gone = bool(old_handle) and rb.memory.by_handle(old_handle) is None
    handle_fresh = bool(new_handle) and new_handle != old_handle
    re_ok, re_detail = (reopen_check(rb, ent, ("Measurement", "StyleName"))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到新标注"}}))
    checks = {
        "only_one": ent is not None,
        "old_deleted": old_gone,
        "handle_fresh": handle_fresh,
        "measurement_new": close(meas, expected_new, tol),
        "measurement_changed": not close(meas, expected_old, tol),
        "style_kept": bool(style) and style == want_style,
        "reopen": re_ok,
    }
    detail: Dict[str, Any] = {
        "old_handle": old_handle,
        "new_handle": ent.handle if ent else None,
        "measurement_du": meas,
        "measurement_expected_du": float(expected_new),
        "measurement_before_du": float(expected_old),
        "measurement_mm": _mm(meas, rb),
        "style": style,
        "style_expected": want_style,
        "reopen": re_detail,
    }
    return verdict(checks, detail, {"update_info": info})
