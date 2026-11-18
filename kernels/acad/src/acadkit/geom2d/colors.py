"""AutoCAD 索引色（ACI）与真彩互换（数据参照 CADCraft `crates/color`）。

用途：出图前的配色核对、"按颜色筛选实体"、CTB 映射校验——都需要把
ACI 索引翻成 RGB，而这个表 AutoCAD 不通过 COM 给我们。
"""

from __future__ import annotations

from typing import Dict, Tuple

RGB = Tuple[int, int, int]

# ACI 1–9（标准七色 + 两档灰）；7 号是"随背景"（黑底白、白底黑），这里取白
BASIC: Dict[int, RGB] = {
    1: (255, 0, 0),        # red
    2: (255, 255, 0),      # yellow
    3: (0, 255, 0),        # green
    4: (0, 255, 255),      # cyan
    5: (0, 0, 255),        # blue
    6: (255, 0, 255),      # magenta
    7: (255, 255, 255),    # white/black（随背景）
    8: (128, 128, 128),    # dark grey
    9: (192, 192, 192),    # light grey
}

# 250–255 是灰度阶梯（AutoCAD 标准）
GRAYS: Dict[int, RGB] = {
    250: (51, 51, 51),
    251: (80, 80, 80),
    252: (105, 105, 105),
    253: (130, 130, 130),
    254: (190, 190, 190),
    255: (255, 255, 255),
}


def aci_to_rgb(index: int) -> RGB:
    """ACI → RGB。10–249 用 AutoCAD 的 HSV 阶梯近似（每 10 个一号）。"""
    if index in BASIC:
        return BASIC[index]
    if index in GRAYS:
        return GRAYS[index]
    if not 10 <= index <= 249:
        raise ValueError("ACI 索引越界：%r" % index)
    # 10..249：每 10 个色相一组，组内亮度递减
    idx = index - 10
    hue = (idx // 10) * 15                     # 0..345 度
    level = idx % 10                           # 0..9
    sat = 1.0
    val = 1.0 - 0.07 * level
    return _hsv_to_rgb(hue, sat, val)


def _hsv_to_rgb(h: float, s: float, v: float) -> RGB:
    import colorsys

    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, s, v)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def rgb_to_aci(rgb: RGB) -> int:
    """RGB → 最接近的 ACI（先试基本色与灰度，再扫 10–249）。"""
    best, best_d = 7, None
    for idx in list(BASIC) + list(GRAYS) + list(range(10, 250)):
        c = aci_to_rgb(idx)
        d = sum((a - b) ** 2 for a, b in zip(c, rgb))
        if best_d is None or d < best_d:
            best, best_d = idx, d
    return best


def is_dark(rgb: RGB, threshold: int = 128) -> bool:
    """判断颜色够不够暗（打印在纸上是否能看清）。"""
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) < threshold
