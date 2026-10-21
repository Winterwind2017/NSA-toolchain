"""配合代号（GB/T 1800.1）：IT5–IT11、0–500 mm、孔 H / 轴 h g f e d。

本模块是**纯 Python**，不需要 AutoCAD —— `dim.fit_code` 的判据用独立表值核对
（判据里另有一张小表，见 `judges/fit.py`），避免"拿实现测实现"。

表值单位：IT 与基本偏差都是 µm；返回 mm。
"""

from __future__ import annotations

import re
from typing import Tuple

FIT_RANGES = [3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500]

IT_TABLE = {
    5: [4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27],
    6: [6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40],
    7: [10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63],
    8: [14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97],
    9: [25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155],
    10: [40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250],
    11: [60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400],
}

FUND_DEV = {
    "g": [-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20],
    "f": [-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68],
    "e": [-14, -20, -25, -32, -40, -50, -60, -72, -85, -100, -110, -125, -135],
    "d": [-20, -30, -40, -50, -65, -80, -100, -120, -145, -170, -190, -210, -230],
}


def _index(nominal: float) -> int:
    for i, hi in enumerate(FIT_RANGES):
        if nominal <= hi:
            return i
    raise ValueError("尺寸 %.1f mm 超出配合表范围（0–500 mm）" % nominal)


def fit_deviation(code: str, nominal: float) -> Tuple[float, float]:
    """`H7@50` → (+0.025, 0.0)；`h6@50` → (0.0, -0.016)。查不到就抛错。"""
    m = re.match(r"^([A-Za-z]{1,2})(\d+)$", str(code).strip())
    if not m:
        raise ValueError("配合代号格式应如 H7 / h6 / g6，实得 %r" % (code,))
    letter, grade = m.group(1), int(m.group(2))
    if grade not in IT_TABLE:
        raise ValueError("IT%d 未支持（仅 IT5–IT11）" % grade)
    i = _index(float(nominal))
    it = IT_TABLE[grade][i]
    key = letter.lower()
    is_hole = letter.isupper()
    if key in ("h", "js"):
        return (it / 1000.0, 0.0) if is_hole else (0.0, -it / 1000.0)
    if key not in FUND_DEV:
        raise ValueError("基本偏差 %r 未支持（仅 H/h/g/f/e/d）" % letter)
    if is_hole:
        ei = -FUND_DEV[key][i]
        return ((ei + it) / 1000.0, ei / 1000.0)
    es = FUND_DEV[key][i]
    return (es / 1000.0, (es - it) / 1000.0)
