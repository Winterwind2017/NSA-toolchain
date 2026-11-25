"""对方仓库里有、这里原来缺的那几项。纯计算，不打开 SolidWorks。"""

from __future__ import annotations

import math
import os
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Point = Tuple[float, float]


def reject_false_success(claimed_ok: bool, before: Optional[float], after: Optional[float],
                         min_delta: float = 0.1) -> Dict[str, object]:
    """声称成功但几何量没变，判失败。"""
    changed = before is not None and after is not None and abs(after - before) >= min_delta
    checks = {"claimed_ok": bool(claimed_ok), "geometry_changed": changed}
    return {"ok": bool(claimed_ok and changed), "checks": checks,
            "delta": None if before is None or after is None else after - before}


def parse_tolerance(text: str) -> Dict[str, object]:
    """从尺寸文字里取出名义值和上下偏差。认 10±0.05 和 10 +0.02/-0.01。"""
    raw = (text or "").strip().replace(" ", "")
    if "±" in raw:
        nominal_s, tol_s = raw.split("±", 1)
        tol = float(tol_s)
        return {"nominal": float(nominal_s), "upper": tol, "lower": -tol, "kind": "symmetric"}
    if "+" in raw and "/" in raw:
        nominal_s, rest = raw.split("+", 1)
        upper_s, lower_s = rest.split("/", 1)
        lower = float(lower_s)
        if not lower_s.startswith("-") and not lower_s.startswith("+"):
            lower = -abs(lower)
        return {"nominal": float(nominal_s), "upper": float(upper_s), "lower": lower, "kind": "limits"}
    raise ValueError("认不出公差文字：%s" % text)


def holes_from_cylinders(faces: Sequence[Dict[str, float]]) -> Dict[str, object]:
    """把圆柱面收成孔表。同一半径算同一种孔。"""
    groups: Dict[float, List[Dict[str, float]]] = {}
    for face in faces:
        radius = round(float(face["radius_mm"]), 3)
        groups.setdefault(radius, []).append(face)
    rows = []
    for radius, items in sorted(groups.items()):
        rows.append({
            "diameter_mm": round(radius * 2.0, 3),
            "count": len(items),
            "centers": [(float(item["x"]), float(item["y"])) for item in items],
        })
    return {"ok": bool(rows), "holes": rows, "checks": {"has_holes": bool(rows)}}


def rename_preview(names: Sequence[str], mapping: Dict[str, str]) -> Dict[str, object]:
    """只给出改名对照，不写文件。新名字为空或互相撞车则失败。"""
    used = []
    rows = []
    errors = []
    for old in names:
        new = mapping.get(old, old)
        if not str(new).strip():
            errors.append("空名字：%s" % old)
            continue
        if new in used:
            errors.append("重名：%s" % new)
            continue
        used.append(new)
        rows.append({"from": old, "to": new, "changed": new != old})
    return {"ok": not errors, "rows": rows, "errors": errors}


def copy_target(source: str, target: str) -> Dict[str, object]:
    """复制目标必须是另一个路径。"""
    same = os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(target))
    return {"ok": bool(source and target) and not same,
            "checks": {"different_path": not same}}


def spur_gear_polygon(module: float, teeth: int) -> List[Point]:
    """近似齿廓：齿顶一段、齿根一段，绕一圈。面积必须为正，且落在齿顶圆里。"""
    if module <= 0 or teeth < 6:
        raise ValueError("模数必须为正，齿数至少 6")
    addendum = module * (teeth + 2) / 2.0
    root = max(module * (teeth - 2.5) / 2.0, module)
    points: List[Point] = []
    step = 2.0 * math.pi / teeth
    for i in range(teeth):
        center = i * step
        half = step * 0.28
        gap = step * 0.22
        for angle, radius in (
            (center - half, addendum),
            (center + half, addendum),
            (center + half + gap, root),
            (center + step - half - gap, root),
        ):
            points.append((radius * math.cos(angle), radius * math.sin(angle)))
    return points


def polygon_area(points: Sequence[Point]) -> float:
    area = 0.0
    for (x1, y1), (x2, y2) in zip(points, list(points[1:]) + [points[0]]):
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def sprocket_pitch_diameter(teeth: int, pitch_mm: float) -> float:
    """节圆直径 = 节距 / sin(π/齿数)。"""
    if teeth < 3 or pitch_mm <= 0:
        raise ValueError("齿数至少 3，节距必须为正")
    return pitch_mm / math.sin(math.pi / teeth)


def helix_length(radius_mm: float, pitch_mm: float, turns: float) -> float:
    """螺旋线展开长度。"""
    if radius_mm <= 0 or pitch_mm <= 0 or turns <= 0:
        raise ValueError("半径、螺距、圈数必须为正")
    return turns * math.hypot(2.0 * math.pi * radius_mm, pitch_mm)


def helix_points(radius_mm: float, pitch_mm: float, turns: float, samples: int = 24) -> List[Tuple[float, float, float]]:
    count = max(int(samples), 8)
    points = []
    for i in range(count + 1):
        t = turns * 2.0 * math.pi * i / count
        points.append((
            radius_mm * math.cos(t),
            radius_mm * math.sin(t),
            pitch_mm * turns * i / count,
        ))
    return points


def edges_in_band(edges: Sequence[Dict[str, float]], min_mm: float, max_mm: float) -> List[Dict[str, float]]:
    """按边长挑选。用来做语义选边，而不是把模型上所有边都倒一遍。"""
    if min_mm > max_mm:
        raise ValueError("最短边不能大于最长边")
    return [edge for edge in edges if min_mm <= float(edge["length_mm"]) <= max_mm]


def motion_samples_ok(samples: Sequence[object], out_of_date: bool) -> Dict[str, object]:
    """运动结果过期，或采样少于两点，都不算算完。"""
    enough = len(list(samples)) >= 2
    checks = {"fresh": not out_of_date, "at_least_two_samples": enough}
    return {"ok": all(checks.values()), "checks": checks}


def cjk_text_issues(texts: Sequence[Dict[str, object]], styles: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    """中文文字必须挂在带大字体的样式上。靠得很近的两行文字记为重叠。"""
    issues = []
    placed = []
    for item in texts:
        content = str(item.get("text") or "")
        if any("\u4e00" <= ch <= "\u9fff" for ch in content):
            style = styles.get(str(item.get("style") or ""), {})
            if not style.get("bigfont"):
                issues.append({"rule": "cjk_without_bigfont", "detail": content})
        height = float(item.get("height") or 0)
        x = float(item.get("x") or 0)
        y = float(item.get("y") or 0)
        for other in placed:
            if abs(x - other[0]) < height and abs(y - other[1]) < height:
                issues.append({"rule": "text_overlap", "detail": content})
                break
        placed.append((x, y, height))
    return issues


def write_box_stl(path: str, size_mm: float) -> Dict[str, object]:
    """没有 SolidWorks 时写一个 ASCII STL 方块。文件头必须是 solid。"""
    if size_mm <= 0:
        raise ValueError("尺寸必须为正")
    s = size_mm
    triangles = [
        ((0, 0, 0), (s, 0, 0), (s, s, 0)),
        ((0, 0, 0), (s, s, 0), (0, s, 0)),
        ((0, 0, s), (s, s, s), (s, 0, s)),
        ((0, 0, s), (0, s, s), (s, s, s)),
        ((0, 0, 0), (0, s, 0), (0, s, s)),
        ((0, 0, 0), (0, s, s), (0, 0, s)),
        ((s, 0, 0), (s, 0, s), (s, s, s)),
        ((s, 0, 0), (s, s, s), (s, s, 0)),
        ((0, 0, 0), (s, 0, s), (s, 0, 0)),
        ((0, 0, 0), (0, 0, s), (s, 0, s)),
        ((0, s, 0), (s, s, 0), (s, s, s)),
        ((0, s, 0), (s, s, s), (0, s, s)),
    ]
    lines = ["solid nsa_box"]
    for a, b, c in triangles:
        lines.append(" facet normal 0 0 0")
        lines.append("  outer loop")
        for point in (a, b, c):
            lines.append("   vertex %s %s %s" % point)
        lines.append("  endloop")
        lines.append(" endfacet")
    lines.append("endsolid nsa_box")
    with open(path, "w", encoding="ascii", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return {"ok": True, "path": path, "triangles": len(triangles),
            "checks": {"stl_header": True}}


def write_preview_page(directory: str, frames: Iterable[str]) -> str:
    """一个本地页面，只显示已经抓到的 SolidWorks 窗口帧。"""
    names = [os.path.basename(frame) for frame in frames]
    imgs = "\n".join('<img src="%s" alt="frame">' % name for name in names)
    html = "<!DOCTYPE html><meta charset=\"utf-8\"><title>NSA preview</title>\n" + imgs + "\n"
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "index.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return path
