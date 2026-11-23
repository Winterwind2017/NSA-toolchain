"""参考解：给"真实件"提供可手算/可积分的对照答案。

FEA 的价值取决于对得上什么。方块、圆轴、直板都有教科书公式；一旦换成台阶轴、
变截面支架，就得自己造参考解，否则只能"看着像"。

两条参考解：

1. `series_compliance`：轴向串联柔度
   δ = F · Σ(Li / (E·Ai))
   用于台阶轴、带法兰的轴、任何分段等截面杆。**精确**（每段均匀应变）。

2. `tapered_cantilever`：变截面悬臂
   δ = ∫₀^L P(L−x)² / (E·I(x)) dx，I(x)=b·h(x)³/12，h 线性变化
   端部有厚度时积分收敛（真正的尖角三角形会发散，所以零件要留 tip_height>0）。
   用 Simpson 高密度积分，误差可控（默认 4000 段）。

两者都在"退化情形"下自动回到教科书公式，这一点用测试钉住。
"""

from __future__ import annotations

import math
from typing import Dict, Sequence, Tuple

from .mesh import FeaError


def series_compliance(segments: Sequence[Tuple[float, float]], E: float) -> float:
    """轴向柔度 Σ(Li/(E·Ai))（mm/N）。

    segments: [(length, area)]，单位 mm / mm²。返回单位 mm/N，
    乘载荷 (N) 得位移 (mm)。
    """
    if not segments:
        raise FeaError("segments 不能为空")
    E = float(E)
    if not (E > 0):
        raise FeaError("弹性模量必须为正")
    total = 0.0
    for i, (L, A) in enumerate(segments):
        L = float(L)
        A = float(A)
        if L <= 0 or A <= 0:
            raise FeaError("段 %d 的长度/面积必须为正：L=%r A=%r" % (i, L, A))
        total += L / (E * A)
    return total


def round_area(diameter: float) -> float:
    d = float(diameter)
    if d <= 0:
        raise FeaError("直径必须为正")
    return math.pi * d * d / 4.0


def rectangular_area(width: float, height: float) -> float:
    w, h = float(width), float(height)
    if w <= 0 or h <= 0:
        raise FeaError("宽/高必须为正")
    return w * h


def tapered_cantilever(*, length: float, root_height: float, tip_height: float,
                       width: float, E: float, force: float,
                       samples: int = 4000) -> Dict[str, float]:
    """变截面悬臂端部挠度（Euler-Bernoulli + 数值积分）。

    h(x) = root + (tip − root)·x/L，I(x) = width·h(x)³/12。
    返回 δ 以及 ∫ 的被积函数端点值，便于判断积分是否健康。
    """
    L = float(length)
    h0 = float(root_height)
    h1 = float(tip_height)
    b = float(width)
    E = float(E)
    P = abs(float(force))
    for name, v in (("length", L), ("root_height", h0), ("tip_height", h1),
                    ("width", b), ("E", E)):
        if not (v > 0):
            raise FeaError("%s 必须为正：%r" % (name, v))
    if samples < 10:
        raise FeaError("samples 至少 10")

    n = int(samples)
    if n % 2:
        n += 1

    def integrand(x: float) -> float:
        h = h0 + (h1 - h0) * x / L
        I = b * h ** 3 / 12.0
        return P * (L - x) ** 2 / (E * I)

    step = L / n
    acc = integrand(0.0) + integrand(L)
    for i in range(1, n):
        x = i * step
        acc += (4.0 if i % 2 else 2.0) * integrand(x)
    delta = acc * step / 3.0

    # 等截面检验值（h1==h0 时用闭式解对账）
    I_root = b * h0 ** 3 / 12.0
    closed_form = P * L ** 3 / (3 * E * I_root)
    return {"deflection": delta, "closed_form_constant": closed_form,
            "ratio_to_constant": delta / closed_form if closed_form else float("inf"),
            "integrand_at_root": integrand(0.0), "integrand_at_tip": integrand(L),
            "samples": n, "length": L, "root_height": h0, "tip_height": h1}


def stepped_axial(*, segments: Sequence[Tuple[float, float]], E: float,
                  force: float) -> Dict[str, float]:
    """台阶轴轴向伸长：δ = F · Σ(Li/(E·Ai))。segments: [(length, diameter)]。"""
    if not segments:
        raise FeaError("segments 不能为空")
    pairs = [(float(L), round_area(d)) for L, d in segments]
    comp = series_compliance(pairs, E)
    return {"deflection": abs(float(force)) * comp, "compliance": comp,
            "areas": [a for _l, a in pairs], "total_length": sum(l for l, _a in pairs)}
