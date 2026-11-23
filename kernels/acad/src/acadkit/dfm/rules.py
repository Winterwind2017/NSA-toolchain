"""可制造性检查（DFM）：钣金 / 铣削 / 注塑 / 3D 打印。

借鉴自 text-to-cad 的 `skills/cad`（MIT）——它的价值不在建模，而在**独立复核**：
"AutoCAD/SW 说画成了"和"这个件能不能加工"是两件事，后者需要工艺规则。

设计取舍：
* 只吃**设计描述**（尺寸/角度/间距），不读 CAD 文件——这样离线、可测、无依赖；
* 每条规则给出 `fix`（改哪儿），因为工程师要的是动作，不是评分；
* 严重度只有 error（做不出来）/ warn（能做出但贵或容易废）；
* **合规件必须零告警**（误报会让人不再看报告）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

# 通用最小壁厚参考（ABS/钢，工程经验值，可按材料覆盖）
MIN_WALL_MM = 0.8


class DfmError(ValueError):
    pass


@dataclass
class Finding:
    rule: str
    severity: str            # error | warn
    where: str
    detail: str
    fix: str

    def to_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "where": self.where,
                "detail": self.detail, "fix": self.fix}


@dataclass
class Report:
    process: str
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    @property
    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {"process": self.process, "ok": self.ok, "counts": self.counts,
                "findings": [f.to_dict() for f in self.findings]}

    def to_text(self) -> str:
        if not self.findings:
            return "%s：合规（0 告警）" % self.process
        lines = ["%s：%d 条（%s）" % (self.process, len(self.findings),
                                     ", ".join("%s=%d" % kv for kv in sorted(self.counts.items())))]
        for f in self.findings:
            lines.append("  [%s] %s @%s：%s → %s"
                         % (f.severity, f.rule, f.where, f.detail, f.fix))
        return "\n".join(lines)


def _num(v: object, name: str) -> float:
    try:
        x = float(v)                                  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise DfmError("%s 不是数值：%r" % (name, v)) from None
    if x != x or abs(x) == float("inf"):
        raise DfmError("%s 是非有限数值：%r" % (name, v))
    return x


# ── 钣金 ────────────────────────────────────────────────────────────
def check_sheet_metal(*, thickness: float, bend_radius: float,
                      holes: Sequence[Dict[str, float]] = (),
                      min_flange: Optional[float] = None) -> Report:
    """holes: [{diameter, distance_to_bend}]（孔心到折弯线距离，mm）。"""
    t = _num(thickness, "thickness")
    r = _num(bend_radius, "bend_radius")
    if t <= 0:
        raise DfmError("板厚必须为正")
    rep = Report("sheet-metal")

    if r < t and r > 0:
        rep.findings.append(Finding(
            "bend_radius_lt_thickness", "warn", "折弯半径",
            "R=%.2f < t=%.2f，容易开裂/回弹大" % (r, t),
            "把内折弯半径提到 ≥ t（=%.2f）" % t))
    if r <= 0:
        rep.findings.append(Finding(
            "bend_radius_too_small", "error", "折弯半径",
            "R=%.2f ≤ 0，物理上做不出" % r, "给正的内折弯半径，至少 0.5·t"))

    need = t + r                                   # 孔边到折弯线的最小距离
    for i, hole in enumerate(holes):
        d = _num(hole.get("diameter", 0), "hole[%d].diameter" % i)
        dist = _num(hole.get("distance_to_bend", 1e9), "hole[%d].distance_to_bend" % i)
        if d <= 0:
            rep.findings.append(Finding(
                "hole_diameter_invalid", "error", "孔%d" % i,
                "直径 %.3f ≤ 0" % d, "给正直径"))
            continue
        if d < t:
            rep.findings.append(Finding(
                "hole_smaller_than_thickness", "warn", "孔%d" % i,
                "φ%.2f < t=%.2f，冲头易断、易带料" % (d, t),
                "孔径做到 ≥ t（或改激光/水刀）"))
        # 孔边（不是孔心）到折弯线
        edge = dist - d / 2.0
        if edge < need:
            rep.findings.append(Finding(
                "hole_too_close_to_bend", "error", "孔%d" % i,
                "孔边到折弯线 %.2f < t+R=%.2f，折弯会拉变形" % (edge, need),
                "孔心外移到 ≥ %.2f，或改折弯后再钻孔" % (need + d / 2.0)))

    if min_flange is not None:
        mf = _num(min_flange, "min_flange")
        floor = t + r + 0.5
        if mf < floor:
            rep.findings.append(Finding(
                "flange_too_short", "error", "最小折弯边",
                "%.2f < t+R+0.5=%.2f，夹不住、折不出" % (mf, floor),
                "折弯边加长到 ≥ %.2f" % floor))
    return rep


# ── 铣削 ────────────────────────────────────────────────────────────
def check_milling(*, tool_diameter: float, pockets: Sequence[Dict[str, float]] = (),
                  max_depth_ratio: float = 4.0) -> Report:
    """pockets: [{width, depth, corner_radius}]。"""
    d_tool = _num(tool_diameter, "tool_diameter")
    if d_tool <= 0:
        raise DfmError("刀具直径必须为正")
    rep = Report("milling")
    for i, p in enumerate(pockets):
        w = _num(p.get("width", 0), "pocket[%d].width" % i)
        depth = _num(p.get("depth", 0), "pocket[%d].depth" % i)
        cr = _num(p.get("corner_radius", 0), "pocket[%d].corner_radius" % i)
        if w <= 0 or depth <= 0:
            rep.findings.append(Finding(
                "pocket_invalid", "error", "型腔%d" % i,
                "宽 %.2f / 深 %.2f 必须为正" % (w, depth), "修正尺寸"))
            continue
        ratio = depth / w
        if ratio > max_depth_ratio:
            rep.findings.append(Finding(
                "depth_ratio_too_high", "error", "型腔%d" % i,
                "深宽比 %.2f > %.1f，长刀让刀严重、效率低" % (ratio, max_depth_ratio),
                "加宽到 ≥ %.2f，或分两道工序（先粗后精/翻面）" % (depth / max_depth_ratio)))
        if w < d_tool:
            rep.findings.append(Finding(
                "pocket_narrower_than_tool", "error", "型腔%d" % i,
                "宽 %.2f < 刀具 φ%.2f，刀进不去" % (w, d_tool),
                "换 φ≤%.2f 的刀，或把槽宽放到 ≥ %.2f" % (w, d_tool)))
        if cr < d_tool / 2.0 - 1e-9:
            rep.findings.append(Finding(
                "corner_radius_too_small", "warn", "型腔%d" % i,
                "内角 R%.2f < 刀半径 %.2f，中心会残留" % (cr, d_tool / 2.0),
                "内角放到 R≥%.2f，或用清角工序（成本更高）" % (d_tool / 2.0)))
    return rep


# ── 注塑 ────────────────────────────────────────────────────────────
def check_injection(*, walls: Sequence[float] = (), draft_deg: float = 0.0,
                    ribs: Sequence[Dict[str, float]] = (),
                    wall_range: tuple = (0.8, 4.0)) -> Report:
    """walls: 各处壁厚；ribs: [{thickness, height}]。"""
    lo, hi = wall_range
    rep = Report("injection")
    vals = [_num(w, "wall") for w in walls]
    for i, w in enumerate(vals):
        if w < lo:
            rep.findings.append(Finding(
                "wall_too_thin", "error", "壁厚%d" % i,
                "%.2f < %.2f，注不满/短射" % (w, lo),
                "加厚到 ≥ %.2f，或换流动性更好的料" % lo))
        elif w > hi:
            rep.findings.append(Finding(
                "wall_too_thick", "warn", "壁厚%d" % i,
                "%.2f > %.2f，缩痕/冷却慢/用料多" % (w, hi),
                "减到 ≤ %.2f，或改中空/加强筋结构" % hi))
    if len(vals) >= 2:
        ratio = max(vals) / min(vals)
        if ratio > 1.5:
            rep.findings.append(Finding(
                "wall_variation", "warn", "壁厚比例",
                "最厚/最薄 = %.2f > 1.5，收缩不均导致翘曲" % ratio,
                "把壁厚差压到 1.5 倍以内（薄处加筋、厚处挖空）"))

    d = _num(draft_deg, "draft_deg")
    if d < 0.5:
        rep.findings.append(Finding(
            "draft_too_small", "error", "脱模斜度",
            "%.2f° < 0.5°，基本脱不出来" % d, "斜面做到 ≥ 1°（纹理面 ≥ 2°）"))
    elif d < 1.0:
        rep.findings.append(Finding(
            "draft_marginal", "warn", "脱模斜度",
            "%.2f° 偏小，量产易拉伤" % d, "提到 ≥ 1°，纹理面 ≥ 2°"))

    nominal = (sum(vals) / len(vals)) if vals else None
    for i, rib in enumerate(ribs):
        t_r = _num(rib.get("thickness", 0), "rib[%d].thickness" % i)
        h_r = _num(rib.get("height", 0), "rib[%d].height" % i)
        if nominal and t_r > 0.6 * nominal + 1e-9:
            rep.findings.append(Finding(
                "rib_too_thick", "warn", "加强筋%d" % i,
                "筋厚 %.2f > 0.6×壁厚 %.2f，对面会有缩痕" % (t_r, 0.6 * nominal),
                "筋厚降到 ≤ %.2f" % (0.6 * nominal)))
        if h_r > 3 * t_r and t_r > 0:
            rep.findings.append(Finding(
                "rib_too_tall", "warn", "加强筋%d" % i,
                "高厚比 %.1f > 3，容易顶白/困气" % (h_r / t_r),
                "降到 ≤ 3 倍，或加斜顶/多级筋"))
    return rep


# ── 3D 打印 ─────────────────────────────────────────────────────────
def check_print3d(*, min_wall: float, overhang_deg: float = 45.0,
                  nozzle: float = 0.4, holes: Sequence[float] = ()) -> Report:
    rep = Report("print3d")
    w = _num(min_wall, "min_wall")
    n = _num(nozzle, "nozzle")
    o = _num(overhang_deg, "overhang_deg")
    if w <= 0 or n <= 0:
        raise DfmError("壁厚/喷嘴必须为正")
    if w < 2 * n:
        rep.findings.append(Finding(
            "wall_thin_for_nozzle", "error", "最小壁厚",
            "%.2f < 2×喷嘴 %.2f，打不出完整两道" % (w, 2 * n),
            "壁厚做到 ≥ %.2f" % (2 * n)))
    if o > 45.0:
        rep.findings.append(Finding(
            "overhang_too_steep", "warn", "悬垂角",
            "%.0f° > 45°，需要支撑（费料、留痕）" % o,
            "把悬垂压到 ≤ 45°，或加 45° 倒角自支撑"))
    for i, h in enumerate(holes):
        hd = _num(h, "hole[%d]" % i)
        if hd < 2 * n:
            rep.findings.append(Finding(
                "hole_below_nozzle", "warn", "孔%d" % i,
                "φ%.2f < 2×喷嘴 %.2f，小孔会打糊/堵" % (hd, 2 * n),
                "孔径放到 ≥ %.2f，或打印后钻孔" % (2 * n)))
    return rep


def check_any(process: str, **kwargs: object) -> Report:
    """按工艺名分发：sheet_metal / milling / injection / print3d。"""
    table = {"sheet_metal": check_sheet_metal, "sheet-metal": check_sheet_metal,
             "milling": check_milling, "injection": check_injection,
             "print3d": check_print3d, "3d-print": check_print3d}
    fn = table.get(process)
    if fn is None:
        raise DfmError("未知工艺：%r（可用：%s）" % (process, ", ".join(sorted(table))))
    return fn(**kwargs)                            # type: ignore[arg-type]
