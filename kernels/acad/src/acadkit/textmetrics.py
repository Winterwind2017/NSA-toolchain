"""文字宽度估算（`cc.fonts.shx` 的落地形态）。

上游 `crates/fonts` 解析 SHX（AutoCAD 编译过的字形文件）。我们**不移植**它，原因写清楚：

* SHX 是未公开的二进制格式，解析成本高、收益低——我们不需要渲染字形，
  只需要知道"这段文字大概多宽"，用来排版、判断是否压线/重叠；
* AutoCAD 自己会算宽度，但我们**不能问它**（判据要独立）。

所以这里给一个**近似字宽模型**：ASCII 按类别给宽度比例，CJK 按全角，
可乘字高与宽度因子。精度足够做排版检查（容差 ±10% 已写进测试）。
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

# 常见西文字符宽度（相对字高，取 AutoCAD 常用 SHX 的经验值）
_NARROW = set("iljI1.,:;'`|![](){}")
_WIDE = set("mwMW@%&")
_DIGIT = set("0123456789")

WIDTH_NARROW = 0.28
WIDTH_DIGIT = 0.50
WIDTH_WIDE = 0.85
WIDTH_UPPER = 0.62
WIDTH_LOWER = 0.48
WIDTH_CJK = 1.00
WIDTH_SPACE = 0.30
WIDTH_DEFAULT = 0.55


def char_width_units(ch: str) -> float:
    """单个字符的宽度（单位 = 字高）。"""
    if ch == " ":
        return WIDTH_SPACE
    if ch == "\t":
        return WIDTH_SPACE * 4
    code = ord(ch)
    if code > 0x2E7F:                     # CJK / 全角
        return WIDTH_CJK
    if ch in _NARROW:
        return WIDTH_NARROW
    if ch in _WIDE:
        return WIDTH_WIDE
    if ch in _DIGIT:
        return WIDTH_DIGIT
    if ch.isupper():
        return WIDTH_UPPER
    if ch.islower():
        return WIDTH_LOWER
    return WIDTH_DEFAULT


def text_width(text: str, height: float, *, width_factor: float = 1.0) -> float:
    """单行文字宽度（单位与 height 相同）。"""
    if height <= 0:
        raise ValueError("字高必须为正")
    if width_factor <= 0:
        raise ValueError("宽度因子必须为正")
    return sum(char_width_units(ch) for ch in text) * height * width_factor


def line_count(text: str) -> int:
    return max(1, len(text.split("\n")))


def mtext_width(text: str, height: float, *, width_factor: float = 1.0,
                line_spacing: float = 1.0) -> Dict[str, float]:
    """多行文字：返回最宽行宽与总高（行距按 1.0 倍字高起算）。"""
    lines = text.split("\n")
    widest = max((text_width(ln, height, width_factor=width_factor) for ln in lines),
                 default=0.0)
    return {"width": widest, "height": height * line_spacing * len(lines)}


def fits_without_overlap(boxes: Sequence[Dict[str, float]], *, tol: float = 0.0
                         ) -> List[tuple]:
    """粗查矩形文字框两两重叠（axis-aligned）。返回重叠对的下标。"""
    bad: List[tuple] = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            ax2, ay2 = a["x"] + a["w"], a["y"] + a["h"]
            bx2, by2 = b["x"] + b["w"], b["y"] + b["h"]
            if (a["x"] + tol < bx2 and b["x"] + tol < ax2
                    and a["y"] + tol < by2 and b["y"] + tol < ay2):
                bad.append((i, j))
    return bad


def estimate_layout(lines: Iterable[Dict[str, object]], *, height: float,
                    width_factor: float = 1.0) -> List[Dict[str, float]]:
    """把 [(text, x, y)] 估成矩形框，便于查重叠。

    行高按 1.25×字高（AutoCAD 单行文字默认框高经验值）。
    """
    out: List[Dict[str, float]] = []
    for item in lines:
        text = str(item.get("text", ""))
        info = mtext_width(text, height, width_factor=width_factor)
        out.append({"x": float(item.get("x", 0.0)), "y": float(item.get("y", 0.0)),
                    "w": info["width"], "h": height * 1.25})
    return out
