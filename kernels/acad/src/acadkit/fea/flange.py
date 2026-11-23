"""法兰/短粗连接件的简化校核（**不是 FEA**，是工程公式，逐条可手算）。

为什么要单独一层：法兰 Ø120×t10 的细长比只有 0.10，一维杆公式与梁理论都不适用
（FEA 那一层会直接拒算）。但工程上对这类件真正要问的不是"整体拉伸位移"，
而是三件事：

1. **螺栓夹紧区局部承压**：预紧力压在垫圈投影面积上，别把法兰面压塌；
2. **法兰板条弯曲**：把法兰环展开成 n 块悬臂板条，受螺栓力，算弯曲应力；
3. **孔边距**：螺栓孔到外缘要有足够边距，否则撕裂。

三个公式都是闭式的，输入只有尺寸与载荷，所以每个数都能手算复核。
输出沿用 DFM 的 `Report`（rule/severity/detail/fix），便于与可制造性一起汇总。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

from ..dfm.rules import Finding, Report


def _pos(v: float, name: str) -> float:
    x = float(v)
    if x != x or abs(x) == float("inf") or x <= 0:
        raise ValueError("%s 必须是有限正数：%r" % (name, v))
    return x


def flange_check(*, outer_d: float, bore_d: float, thickness: float,
                 bolt_count: int, bolt_d: float, bcd: float,
                 preload_per_bolt: float,
                 sigma_allow: float = 140.0,
                 bearing_allow: float = 200.0,
                 washer_d: Optional[float] = None,
                 min_edge_margin: float = 1.2) -> Report:
    """返回 Report("flange")，findings 为空表示三项都过。

    参数单位：mm / N / MPa。
    * preload_per_bolt：单个螺栓的预紧力（不是外载）；
    * sigma_allow：法兰材料许用弯曲应力；
    * bearing_allow：许用挤压（承压）应力，钢-钢约 150~250 MPa；
    * washer_d：垫圈外径，默认 1.5×bolt_d；
    * min_edge_margin：孔心到外缘的最小倍数（× 螺栓孔径）。
    """
    Do = _pos(outer_d, "outer_d")
    Di = _pos(bore_d, "bore_d")
    t = _pos(thickness, "thickness")
    n = int(bolt_count)
    db = _pos(bolt_d, "bolt_d")
    bcd = _pos(bcd, "bcd")
    F = _pos(preload_per_bolt, "preload_per_bolt")
    dw = _pos(washer_d if washer_d else 1.5 * db, "washer_d")
    rep = Report("flange")

    if Di >= Do:
        raise ValueError("内孔必须小于外径")
    if n < 1:
        raise ValueError("螺栓数量必须 ≥1")
    if bcd / 2.0 + db / 2.0 > Do / 2.0:
        rep.findings.append(Finding(
            "bolt_circle_outside", "error", "螺栓分布圆",
            "bcd/2+db/2 = %.2f > 外半径 %.2f，螺栓超出法兰" % (bcd / 2 + db / 2, Do / 2),
            "减小 bcd 或加大外径"))

    # 1) 局部承压：预紧力 / 垫圈投影面积
    area_bearing = math.pi / 4.0 * (dw ** 2 - db ** 2)
    sigma_b = F / area_bearing if area_bearing > 0 else float("inf")
    if sigma_b > bearing_allow:
        rep.findings.append(Finding(
            "bearing_overstress", "error", "螺栓承压",
            "σ_b = %.1f MPa > %.0f（垫圈 Ø%g）" % (sigma_b, bearing_allow, dw),
            "加大垫圈到 Ø≥%.1f，或降低预紧力/改用更大螺栓"
            % (math.sqrt(db ** 2 + 4 * F / (math.pi * bearing_allow)))))

    # 2) 法兰板条弯曲：把环展开成 n 块悬臂板条，长 = (Do - Dm)/2，宽 = πDm/n
    Dm = bcd
    arm = max((Do - Dm) / 2.0, 1e-9)
    strip_w = math.pi * Dm / n
    I = strip_w * t ** 3 / 12.0
    M = F * arm
    sigma_w = M * (t / 2.0) / I
    if sigma_w > sigma_allow:
        need_t = math.sqrt(6.0 * M / (strip_w * sigma_allow))
        rep.findings.append(Finding(
            "flange_bending_overstress", "error", "法兰板条弯曲",
            "σ = %.1f MPa > %.0f（力臂 %.1f，板条宽 %.1f）"
            % (sigma_w, sigma_allow, arm, strip_w),
            "法兰加厚到 ≥ %.2f mm（当前 %.2f）" % (need_t, t)))
    elif sigma_w > 0.8 * sigma_allow:
        headroom = sigma_allow / sigma_w
        rep.findings.append(Finding(
            "flange_bending_marginal", "warn", "法兰板条弯曲",
            "σ = %.1f MPa 已达许用的 %.0f%%（余量 %.2f×）"
            % (sigma_w, sigma_w / sigma_allow * 100, headroom),
            "预紧力最多可到 %.0f N（当前 %.0f）；再往上就得加厚到 %.2f mm"
            % (F * headroom, F, math.sqrt(6.0 * M / (strip_w * sigma_allow)) * 1.05)))

    # 3) 孔边距：孔心到外缘
    margin = (Do - bcd) / 2.0
    need = (min_edge_margin - 0.5) * db          # 孔边到外缘 ≥ 0.7db 的常用下限
    if margin < need:
        rep.findings.append(Finding(
            "bolt_edge_margin", "error", "螺栓孔边距",
            "孔心到外缘 %.2f < %.2f（≈%.1f×db）" % (margin, need, need / db),
            "减小 bcd 或加大外径到 ≥ %.1f" % (bcd + 2 * need)))
    return rep
