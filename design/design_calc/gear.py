"""
齿轮几何、种类推荐、弯曲初校

公式来源: GB/T 3480 简化 / Shigley Lewis、BV13t896UEWL P12 大纲。
完整接触强度见 design_knowledge/03-机构设计/传动设计.md。
"""

from __future__ import annotations

import math


STANDARD_MODULES = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]

_ALLOW_BEND = {
    "45QT": 200.0,
    "40Cr": 280.0,
    "20CrMnTi": 350.0,
    "POM": 40.0,
}


def geometry(module: float, z1: int, z2: int) -> dict:
    """标准变位直齿几何。长度 mm。"""
    if module <= 0 or z1 < 1 or z2 < 1:
        raise ValueError("module / z 必须为正")
    d1 = module * z1
    d2 = module * z2
    return {
        "module": module,
        "z1": z1,
        "z2": z2,
        "d1_mm": d1,
        "d2_mm": d2,
        "da1_mm": d1 + 2 * module,
        "da2_mm": d2 + 2 * module,
        "df1_mm": d1 - 2.5 * module,
        "df2_mm": d2 - 2.5 * module,
        "center_distance_mm": module * (z1 + z2) / 2.0,
        "ratio": z2 / z1,
        "undercut_risk": z1 < 17,
    }


def base_radius_mm(module: float, teeth: int, pressure_angle_deg: float = 20.0) -> float:
    """标准直齿基圆半径。"""
    if module <= 0 or teeth < 1:
        raise ValueError("module / teeth 必须为正")
    return module * teeth / 2.0 * math.cos(math.radians(pressure_angle_deg))


def pitch_roll(pressure_angle_deg: float = 20.0) -> float:
    """分度圆处的展开角，tan α。"""
    return math.tan(math.radians(pressure_angle_deg))


def involute_xy(base_radius_mm: float, roll: float) -> tuple[float, float]:
    """
    渐开线一点，基圆上 roll=0 时位于 (rb, 0)。

    分度圆展开角用 pitch_roll()。这里只给齿廓坐标，不生成 SolidWorks 特征。
    """
    if base_radius_mm <= 0:
        raise ValueError("基圆半径必须大于 0")
    if roll < 0:
        raise ValueError("展开角不能为负")
    return (
        base_radius_mm * (math.cos(roll) + roll * math.sin(roll)),
        base_radius_mm * (math.sin(roll) - roll * math.cos(roll)),
    )


def pitch_speed_m_s(d_mm: float, rpm: float) -> float:
    """圆周速度 m/s。"""
    return math.pi * d_mm * rpm / 60000.0


def recommend_form(
    axes: str = "parallel",
    ratio: float = 2.0,
    speed_m_s: float = 2.0,
    quiet: bool = False,
    positioning: bool = False,
    buy_reducer_ok: bool = True,
) -> dict:
    """
    先定齿形种类或直接改减速机。

    axes: 'parallel' / 'intersecting' / 'skew' / 'linear'
    """
    notes: list = []
    if positioning and buy_reducer_ok and axes != "linear":
        return {
            "form": "伺服+行星/谐波减速机",
            "reason": "定位轴开式齿轮换向空程大，优先买减速机",
            "notes": notes,
            "next": "reducer.recommend_type",
        }

    if axes == "linear":
        return {
            "form": "齿轮齿条",
            "reason": "转动变长行程直线",
            "notes": notes + ["消隙；先 transmission.recommend_drive"],
            "next": "transmission.recommend_drive",
        }
    if axes == "intersecting":
        return {
            "form": "锥齿轮",
            "reason": "相交轴换向",
            "notes": notes + ["按样本选，不要现场发明锥角"],
            "next": "厂家锥齿样本",
        }
    if axes == "skew" or (axes == "parallel" and ratio >= 20):
        form = "蜗轮蜗杆" if ratio >= 10 else "斜齿圆柱"
        return {
            "form": form,
            "reason": "大速比或交错轴",
            "notes": notes + ["蜗轮效率低、发热，连续工作要算热功率"],
            "next": "厂家蜗轮样本" if "蜗" in form else "gear.geometry",
        }

    if quiet or speed_m_s >= 6:
        notes.append("直齿圆周速度建议 <6 m/s；再高用斜齿并处理轴向力")
        return {
            "form": "斜齿圆柱齿轮",
            "reason": "要安静或线速度偏高",
            "notes": notes,
            "next": "gear.bending_check",
        }
    return {
        "form": "直齿圆柱齿轮",
        "reason": "平行轴默认：便宜、无轴向力",
        "notes": notes + ["z1≥17；能买样本就不要定制"],
        "next": "gear.suggest_module",
    }


def suggest_module(
    torque_nm: float,
    z1: int = 18,
    material: str = "45QT",
    kf: float = 1.5,
    face_width_factor: float = 10.0,
) -> dict:
    """
    按弯曲粗估模数：假设 b = face_width_factor · m，再圆整到标准模数。
    """
    if torque_nm <= 0 or z1 < 12:
        raise ValueError("torque_nm > 0 且 z1 ≥ 12")
    sigma_allow = _ALLOW_BEND.get(material, 200.0)
    yf = max(0.154 - 0.912 / z1, 0.2)
    # σ = 2T/(z m) * KF / (b m YF), b = k m  →  m³ = 2T KF / (z k YF [σ])
    # T in N·mm = torque_nm * 1000
    t_nmm = torque_nm * 1000.0
    m3 = 2.0 * t_nmm * kf / (z1 * face_width_factor * yf * sigma_allow)
    m_calc = m3 ** (1.0 / 3.0)
    m_std = next((m for m in STANDARD_MODULES if m >= m_calc), STANDARD_MODULES[-1])
    b = face_width_factor * m_std
    warnings = []
    if z1 < 17:
        warnings.append("z1<17 有根切风险，做正变位或加齿")
    if material == "POM":
        warnings.append("塑料齿轮按厂家许用扭矩，此模数只是量级")
    return {
        "module_calc_mm": round(m_calc, 3),
        "module_mm": m_std,
        "z1": z1,
        "face_width_mm": round(b, 1),
        "material": material,
        "warnings": warnings,
    }


def bending_check(
    torque_nm: float,
    module: float,
    z: int,
    face_width_mm: float,
    material: str = "45QT",
    kf: float = 1.5,
) -> dict:
    """Lewis 简化弯曲应力，许用见 传动设计.md。"""
    d = module * z
    ft = 2.0 * torque_nm * 1000.0 / d  # N
    yf = max(0.154 - 0.912 / z, 0.2)
    sigma = ft * kf / (face_width_mm * module * yf)
    allow = _ALLOW_BEND.get(material, 200.0)
    sf = allow / sigma if sigma > 0 else 999.0
    return {
        "tangential_force_N": round(ft, 1),
        "sigma_F_MPa": round(sigma, 1),
        "allow_MPa": allow,
        "safety": round(sf, 2),
        "pass": sf >= 1.25,
        "yf": round(yf, 3),
    }


def pair_summary(
    torque_nm: float,
    rpm_pinion: float,
    ratio: float = 2.0,
    z1: int = 17,
    material: str = "45QT",
) -> dict:
    """一对平行轴直齿的初选汇总。"""
    z2 = max(int(round(z1 * ratio)), z1 + 1)
    sug = suggest_module(torque_nm, z1=z1, material=material)
    m = sug["module_mm"]
    geo = geometry(m, z1, z2)
    b1 = sug["face_width_mm"]
    b2 = max(b1 - 10.0, 0.8 * b1)  # 大轮略窄
    chk = bending_check(torque_nm, m, z1, b1, material)
    v = pitch_speed_m_s(geo["d1_mm"], rpm_pinion)
    notes = list(sug["warnings"])
    if v >= 6:
        notes.append(f"圆周速度 {v:.1f} m/s ≥6，改斜齿或减速机")
    if geo["undercut_risk"]:
        notes.append("小轮根切风险")
    return {
        "geometry": geo,
        "module_mm": m,
        "b1_mm": b1,
        "b2_mm": round(b2, 1),
        "pitch_speed_m_s": round(v, 2),
        "bending": chk,
        "notes": notes,
    }
