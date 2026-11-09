"""P&ID 符号：程序化绘制（闸阀 / 离心泵 / 仪表气泡）。

本机没有安装 P&ID 符号库（`SL_DIR/pid/` 不存在），所以按 ISA 画法**程序化**
画出来：不依赖任何外部图块，`<<VANILLA>>` 下即可交付。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..core import com
from .helpers import add, ms_of, pt

# 三种符号的线段（世界坐标，单位 mm）
VALVE_LINES: List[Tuple[Tuple[float, float], Tuple[float, float]]] = [
    ((-12, -8), (-12, 8)), ((-12, 8), (0, 0)), ((0, 0), (-12, -8)),
    ((12, -8), (12, 8)), ((12, 8), (0, 0)), ((0, 0), (12, -8)),
    ((0, 0), (0, 14)), ((-5, 14), (5, 14)),
]
PUMP_LINES: List[Tuple[Tuple[float, float], Tuple[float, float]]] = [
    ((45, 0), (57, 6)), ((57, 6), (57, -6)), ((57, -6), (45, 0)),
    ((25, 0), (35, 0)), ((45, 10), (45, 22)),
]
BUBBLE_LINES: List[Tuple[Tuple[float, float], Tuple[float, float]]] = [
    ((83, 0), (97, 0)),
]
TEXTS: List[Tuple[Tuple[float, float], float, str]] = [
    ((-10, -20), 3.0, "HV-01"),
    ((40, -20), 3.0, "P-01"),
    ((84, -1.5), 2.5, "PI-01"),
]


def build_pid_symbols(doc: Any, ctx: Dict[str, Any]) -> None:
    ms = ms_of(doc)
    for p, q in VALVE_LINES + PUMP_LINES + BUBBLE_LINES:
        add(ms, "AddLine", pt(p[0], p[1], 0), pt(q[0], q[1], 0), label="AddLine")
    add(ms, "AddCircle", pt(45, 0, 0), 10.0, label="AddCircle")     # 泵体
    add(ms, "AddCircle", pt(90, 0, 0), 7.0, label="AddCircle")      # 仪表气泡
    for p, h, text in TEXTS:
        add(ms, "AddText", text, pt(p[0], p[1], 0), h, label="AddText")
    ctx["artifacts"]["pid"] = {
        "lines": len(VALVE_LINES) + len(PUMP_LINES) + len(BUBBLE_LINES),
        "circles": 2, "texts": [t[2] for t in TEXTS],
    }
