"""
强度校核工具

公式来源: Hibbeler《材料力学》、Shigley《机械设计》
"""

import math
from typing import Optional


def von_mises_plane(sx: float, sy: float, txy: float) -> float:
    """von Mises 等效应力 (平面应力)"""
    return math.sqrt(sx**2 - sx * sy + sy**2 + 3 * txy**2)


def von_mises_3d(s1: float, s2: float, s3: float) -> float:
    """von Mises 等效应力 (三向主应力)"""
    return math.sqrt(0.5 * ((s1 - s2)**2 + (s2 - s3)**2 + (s3 - s1)**2))


def bending_stress(M: float, c: float, I: float) -> float:
    """弯曲正应力 σ = M·c / I"""
    return M * c / I if I > 0 else float('inf')


def torsion_stress(T: float, r: float, J: float) -> float:
    """扭转剪应力 τ = T·r / J"""
    return T * r / J if J > 0 else float('inf')


def combined_bending_torsion(M: float, T: float, S: float) -> float:
    """弯扭组合 von Mises (用截面模量 S)"""
    sigma = M / S if S > 0 else 0
    tau = T / (2 * S) if S > 0 else 0  # 圆截面 Wt = 2W
    return von_mises_plane(sigma, 0, tau)


def axial_stress(F: float, A: float) -> float:
    """轴向正应力"""
    return F / A if A > 0 else float('inf')


def euler_buckling(E: float, I: float, L: float, K: float = 1.0) -> float:
    """欧拉临界载荷"""
    return math.pi**2 * E * I / (K * L)**2


def beam_deflection_cantilever(F: float, L: float, E: float, I: float) -> float:
    """悬臂梁端部集中力挠度"""
    return F * L**3 / (3 * E * I)


def beam_deflection_simple_center(F: float, L: float, E: float, I: float) -> float:
    """简支梁中点集中力挠度"""
    return F * L**3 / (48 * E * I)


def beam_deflection_simple_uniform(w: float, L: float, E: float, I: float) -> float:
    """简支梁均布载荷中点挠度"""
    return 5 * w * L**4 / (384 * E * I)


# ─── 截面属性 ────────────────────────────────────────────────

def rect_I(b: float, h: float) -> float:
    """矩形截面惯性矩 I = b·h³/12"""
    return b * h**3 / 12


def rect_S(b: float, h: float) -> float:
    """矩形截面模量 S = b·h²/6"""
    return b * h**2 / 6


def circle_I(d: float) -> float:
    """圆形截面惯性矩 I = π·d⁴/64"""
    return math.pi * d**4 / 64


def circle_S(d: float) -> float:
    """圆形截面模量 S = π·d³/32"""
    return math.pi * d**3 / 32


def circle_J(d: float) -> float:
    """圆形截面极惯性矩 J = π·d⁴/32"""
    return math.pi * d**4 / 32


def hollow_circle_I(D: float, d: float) -> float:
    """空心圆截面惯性矩"""
    return math.pi * (D**4 - d**4) / 64


def hollow_circle_J(D: float, d: float) -> float:
    """空心圆截面极惯性矩"""
    return math.pi * (D**4 - d**4) / 32


# ─── 疲劳 ────────────────────────────────────────────────────

def marin_surface_finish(Sut: float, finish: str = "machined") -> float:
    """
    Marin 表面状态因子 ka

    Args:
        Sut: 抗拉强度 MPa
        finish: 'ground'/'machined'/'hot_rolled'/'as_forged'
    """
    coeffs = {
        "ground": (1.58, -0.085),
        "machined": (4.51, -0.265),
        "hot_rolled": (57.7, -0.718),
        "as_forged": (272.0, -0.995),
    }
    a, b = coeffs.get(finish, (4.51, -0.265))
    return a * Sut**b


def marin_size_factor(d: float) -> float:
    """Marin 尺寸因子 kb"""
    if d <= 2.79:
        return 1.0
    elif d <= 51:
        return 1.24 * d**(-0.107)
    else:
        return 1.51 * d**(-0.157)


def endurance_limit(Sut: float, ka: float = 1.0, kb: float = 1.0,
                    kc: float = 1.0, kd: float = 1.0, ke: float = 1.0) -> float:
    """
    修正持久极限

    Args:
        Sut: 抗拉强度 MPa
        ka~ke: Marin 修正因子
    """
    Se_prime = 0.5 * Sut if Sut <= 1400 else 700
    return ka * kb * kc * kd * ke * Se_prime


def goodman_safety(sa: float, sm: float, Se: float, Sut: float) -> float:
    """修正 Goodman 安全系数"""
    denom = sa / Se + sm / Sut
    return 1.0 / denom if denom > 0 else float('inf')


def soderberg_safety(sa: float, sm: float, Se: float, Sy: float) -> float:
    """Soderberg 安全系数"""
    denom = sa / Se + sm / Sy
    return 1.0 / denom if denom > 0 else float('inf')


def gerber_safety(sa: float, sm: float, Se: float, Sut: float) -> float:
    """Gerber 安全系数 (需求解二次方程)"""
    if sm == 0:
        return Se / sa if sa > 0 else float('inf')
    # n·sa/Se + (n·sm/Sut)² = 1
    # 令 x = n, 解 a·x² + b·x - 1 = 0
    a = (sm / Sut) ** 2
    b = sa / Se
    disc = b**2 + 4 * a
    n = (-b + math.sqrt(disc)) / (2 * a) if a > 0 else 1.0 / b
    return n
