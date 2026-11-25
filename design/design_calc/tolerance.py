"""
公差与尺寸链计算

公式来源: GB/T 1800~1804、GB/T 1182~1184
"""

import math
from typing import List, Dict


# GB/T 1800 标准公差值 (μm) — 常用尺寸段
# 格式: IT_TABLE[(size_min, size_max)] = {IT_grade: tolerance_um}
IT_TABLE = {
    (1, 3):    {5: 4, 6: 6, 7: 10, 8: 14, 9: 25, 10: 40, 11: 60, 12: 100},
    (3, 6):    {5: 5, 6: 8, 7: 12, 8: 18, 9: 30, 10: 48, 11: 75, 12: 120},
    (6, 10):   {5: 6, 6: 9, 7: 15, 8: 22, 9: 36, 10: 58, 11: 90, 12: 150},
    (10, 18):  {5: 8, 6: 11, 7: 18, 8: 27, 9: 43, 10: 70, 11: 110, 12: 180},
    (18, 30):  {5: 9, 6: 13, 7: 21, 8: 33, 9: 52, 10: 84, 11: 130, 12: 210},
    (30, 50):  {5: 11, 6: 16, 7: 25, 8: 39, 9: 62, 10: 100, 11: 160, 12: 250},
    (50, 80):  {5: 13, 6: 19, 7: 30, 8: 46, 9: 74, 10: 120, 11: 190, 12: 300},
    (80, 120): {5: 15, 6: 22, 7: 35, 8: 54, 9: 87, 10: 140, 11: 220, 12: 350},
    (120, 180):{5: 18, 6: 25, 7: 40, 8: 63, 9: 100, 10: 160, 11: 250, 12: 400},
    (180, 250):{5: 20, 6: 29, 7: 46, 8: 72, 9: 115, 10: 185, 11: 290, 12: 460},
}


def get_it_tolerance(size: float, grade: int) -> float:
    """
    查标准公差值

    Args:
        size: 基本尺寸 mm
        grade: IT 等级 (5~12)

    Returns:
        公差值 μm
    """
    for (lo, hi), grades in IT_TABLE.items():
        if lo < size <= hi or (lo == 1 and size <= hi):
            return grades.get(grade, 0)
    return 0


def tolerance_chain_extreme(rings: List[Dict]) -> Dict:
    """
    尺寸链极值法

    Args:
        rings: [{"nominal": mm, "upper": mm, "lower": mm, "type": "inc"/"dec"}]
               type: "inc" = 增环, "dec" = 减环

    Returns:
        封闭环 {"nominal", "upper", "lower", "tolerance", "max", "min"}
    """
    nom = 0.0
    es = 0.0
    ei = 0.0

    for r in rings:
        if r["type"] == "inc":
            nom += r["nominal"]
            es += r["upper"]
            ei += r["lower"]
        else:
            nom -= r["nominal"]
            es -= r["lower"]
            ei -= r["upper"]

    return {
        "nominal": round(nom, 4),
        "upper": round(es, 4),
        "lower": round(ei, 4),
        "tolerance": round(es - ei, 4),
        "max": round(nom + es, 4),
        "min": round(nom + ei, 4),
    }


def tolerance_chain_statistical(rings: List[Dict]) -> Dict:
    """
    尺寸链统计法 (概率法)

    Args:
        rings: 同极值法格式

    Returns:
        封闭环结果
    """
    nom = 0.0
    tol_sq = 0.0

    for r in rings:
        t = r["upper"] - r["lower"]
        tol_sq += t ** 2
        if r["type"] == "inc":
            nom += r["nominal"]
        else:
            nom -= r["nominal"]

    tol = math.sqrt(tol_sq)
    half = tol / 2

    return {
        "nominal": round(nom, 4),
        "tolerance": round(tol, 4),
        "upper": round(half, 4),
        "lower": round(-half, 4),
        "max": round(nom + half, 4),
        "min": round(nom - half, 4),
    }


def check_fit(hole_code: str, shaft_code: str, size: float) -> Dict:
    """
    配合类型判定

    Args:
        hole_code: 孔公差带代号 如 "H7"
        shaft_code: 轴公差带代号 如 "g6"
        size: 基本尺寸 mm

    Returns:
        dict 配合信息
    """
    # 简化判定: 根据轴的基本偏差字母
    shaft_letter = shaft_code[0].lower()

    clearance_letters = set("abcdefgh")
    transition_letters = set("jkmn")
    interference_letters = set("prstuvwxyz")

    if shaft_letter in clearance_letters:
        fit_type = "间隙配合"
    elif shaft_letter in transition_letters:
        fit_type = "过渡配合"
    else:
        fit_type = "过盈配合"

    return {
        "hole": hole_code,
        "shaft": shaft_code,
        "size_mm": size,
        "fit_type": fit_type,
        "basis": "基孔制" if hole_code[0] == "H" else ("基轴制" if shaft_code[0] == "h" else "混合"),
    }
