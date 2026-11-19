"""动态块模型：参数、可见性状态、夹点（语义参照 CADCraft `cmd/blocks/dyngrip.rs`）。

我们读不了 AutoCAD 的块定义内部结构，但**能读懂 DXF**：动态块的参数与可见性
以扩展数据（XDATA）/扩展字典的形式存在。这个模块给出数据模型与运算，
再用它表达"这个块有哪些参数、切到某个可见性状态时哪些实体可见、某个参数值下夹点在哪"。

只做**纯数据与判定**，不猜 AutoCAD 的内部编码（那要有实测样本再补）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

Vec2 = Tuple[float, float]

PARAM_KINDS = ("linear", "polar", "xy", "rotation", "flip", "visibility", "lookup")


class DynBlockError(ValueError):
    pass


@dataclass
class Parameter:
    name: str
    kind: str
    value: float = 0.0
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    def __post_init__(self) -> None:
        if self.kind not in PARAM_KINDS:
            raise DynBlockError("未知参数类型：%r（可用：%s）"
                                % (self.kind, ", ".join(PARAM_KINDS)))

    def validate(self, value: float) -> float:
        if value != value or abs(value) == float("inf"):
            raise DynBlockError("参数 %s 是非有限数值：%r" % (self.name, value))
        if self.minimum is not None and value < self.minimum:
            raise DynBlockError("参数 %s 小于下限 %r" % (self.name, self.minimum))
        if self.maximum is not None and value > self.maximum:
            raise DynBlockError("参数 %s 大于上限 %r" % (self.name, self.maximum))
        return float(value)


@dataclass
class Grip:
    """夹点：位置 + 关联的参数名（拖动它改哪个参数）。"""

    point: Vec2
    parameter: str
    index: int = 0


@dataclass
class VisibilityState:
    name: str
    visible: Set[str] = field(default_factory=set)      # 实体句柄


@dataclass
class DynamicBlock:
    name: str
    parameters: Dict[str, Parameter] = field(default_factory=dict)
    states: Dict[str, VisibilityState] = field(default_factory=dict)
    grips: List[Grip] = field(default_factory=list)
    current: Optional[str] = None      # 当前可见性状态（切换时作"before"）

    # ── 参数 ──
    def set_value(self, name: str, value: float) -> float:
        p = self.parameters.get(name)
        if p is None:
            raise DynBlockError("没有参数 %r（可用：%s）"
                                % (name, ", ".join(sorted(self.parameters)) or "无"))
        p.value = p.validate(value)
        return p.value

    def get_value(self, name: str) -> float:
        p = self.parameters.get(name)
        if p is None:
            raise DynBlockError("没有参数 %r" % name)
        return p.value

    # ── 可见性 ──
    def visible_entities(self, state: Optional[str] = None) -> Set[str]:
        if state is None:
            if not self.states:
                return set()
            state = self.current or next(iter(self.states))
        st = self.states.get(state)
        if st is None:
            raise DynBlockError("没有可见性状态 %r（可用：%s）"
                                % (state, ", ".join(sorted(self.states)) or "无"))
        return set(st.visible)

    def switch_visibility(self, state: str) -> Dict[str, object]:
        """切换可见性：返回 {before_only, after_only, kept}，供调用方改图。"""
        before = self.visible_entities()
        after = self.visible_entities(state)
        self.current = state
        return {"state": state,
                "hide": sorted(before - after),
                "show": sorted(after - before),
                "kept": sorted(before & after)}

    # ── 夹点 ──
    def grip_points(self, *, stretch_dir: Vec2 = (1.0, 0.0)) -> List[dict]:
        """按当前参数值算夹点位置：linear/xy 沿方向平移，rotation 只报角度。"""
        out: List[dict] = []
        for g in self.grips:
            p = self.parameters.get(g.parameter)
            if p is None:
                out.append({"point": g.point, "parameter": g.parameter,
                            "error": "参数不存在"})
                continue
            if p.kind in ("linear", "xy"):
                dx, dy = stretch_dir
                n = math.hypot(dx, dy) or 1.0
                out.append({"point": (g.point[0] + dx / n * p.value,
                                      g.point[1] + dy / n * p.value),
                            "parameter": p.name, "value": p.value})
            elif p.kind == "rotation":
                out.append({"point": g.point, "parameter": p.name,
                            "angle_deg": p.value})
            else:
                out.append({"point": g.point, "parameter": p.name,
                            "value": p.value})
        return out

    def summary(self) -> Dict[str, object]:
        return {"name": self.name,
                "parameters": {k: v.value for k, v in self.parameters.items()},
                "states": {k: len(v.visible) for k, v in self.states.items()},
                "grips": len(self.grips)}
