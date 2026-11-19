"""出图管线：把"图层/对象/样式表"三层解析成每条实体的最终出图属性。

为什么值得单独做：`plot.style` 只验了"有样式表 vs 无线宽"的墨量差；
真正交付前要回答的是**每条线最终多粗、是不是黑白的**。这些规则 AutoCAD 有
（BYLAYER/BYBLOCK 继承、CTB 映射、透明度），但从不告诉你结果——
这里把规则写成可测函数，于是"这条线应该 0.35mm"就能当判据。

参照 CADCraft `crates/engine` 的 plot 管线分层（样式表 → 线宽 → 透明）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

# DXF 线宽是"百分比毫米"整数：-1=BYLAYER, -2=BYBLOCK, -3=DEFAULT
BYLAYER, BYBLOCK, LWDEFAULT = -1, -2, -3

VALID_LW = {0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90,
            100, 106, 120, 140, 158, 200, 211}

# 常用映射：百分比毫米 → mm
def lw_mm(code: int) -> float:
    return code / 100.0


@dataclass
class LayerStyle:
    name: str
    lineweight: int = BYLAYER
    color: int = 7
    plottable: bool = True
    transparency: int = 0          # 0–90（百分比）


@dataclass
class EntityStyle:
    handle: str
    layer: str
    lineweight: int = BYLAYER
    color: int = 256               # 256 = BYLAYER
    transparency: int = 0


@dataclass
class ResolvedStyle:
    handle: str
    layer: str
    lineweight_mm: float
    color: int
    plottable: bool
    transparency: int
    source: Dict[str, str] = field(default_factory=dict)   # 每个值从哪来的


class PlotPlanError(ValueError):
    pass


def _check_lw(code: int) -> int:
    if code in (BYLAYER, BYBLOCK, LWDEFAULT) or code in VALID_LW:
        return code
    raise PlotPlanError("非法线宽值 %r（必须是 BYLAYER/BYBLOCK/DEFAULT 或标准档位）" % code)


def resolve(entity: EntityStyle, layers: Dict[str, LayerStyle], *,
            default_lw: int = 25) -> ResolvedStyle:
    """把一条实体的出图属性解析出来（BYLAYER 继承图层）。"""
    layer = layers.get(entity.layer)
    if layer is None:
        raise PlotPlanError("实体 %s 引用了不存在的图层 %r"
                            % (entity.handle, entity.layer))
    _check_lw(entity.lineweight)
    _check_lw(layer.lineweight)

    if entity.lineweight == BYLAYER or entity.lineweight == BYBLOCK:
        lw_code, lw_src = layer.lineweight, "layer"
    else:
        lw_code, lw_src = entity.lineweight, "entity"
    if lw_code in (BYLAYER, BYBLOCK, LWDEFAULT):
        lw_code, lw_src = default_lw, "default"

    color = entity.color if entity.color not in (256, 0) else layer.color
    return ResolvedStyle(handle=entity.handle, layer=entity.layer,
                         lineweight_mm=lw_mm(lw_code), color=color,
                         plottable=layer.plottable,
                         transparency=max(layer.transparency, entity.transparency),
                         source={"lineweight": lw_src,
                                 "color": "entity" if entity.color not in (256, 0) else "layer"})


@dataclass
class PlotPlan:
    items: List[ResolvedStyle] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def omitted(self) -> List[str]:
        return [i.handle for i in self.items if not i.plottable]

    def lineweight_histogram(self) -> Dict[float, int]:
        out: Dict[float, int] = {}
        for i in self.items:
            if not i.plottable:
                continue
            out[i.lineweight_mm] = out.get(i.lineweight_mm, 0) + 1
        return dict(sorted(out.items()))

    def to_dict(self) -> dict:
        return {"count": len(self.items), "omitted": self.omitted,
                "histogram": self.lineweight_histogram(), "warnings": self.warnings}


def build_plan(entities: Sequence[EntityStyle],
               layers: Dict[str, LayerStyle], *,
               default_lw: int = 25,
               expect_lineweight_variety: bool = True) -> PlotPlan:
    """解析整张图，并给出交付前该关注的告警。"""
    plan = PlotPlan()
    for e in entities:
        plan.items.append(resolve(e, layers, default_lw=default_lw))

    plotted = [i for i in plan.items if i.plottable]
    hist = plan.lineweight_histogram()
    if not plotted:
        plan.warnings.append("没有任何可出图实体")
    elif expect_lineweight_variety and len(hist) == 1:
        plan.warnings.append("所有实体线宽都是 %s mm——检查是否忘了设图层线宽"
                             % next(iter(hist)))
    thin = [i.handle for i in plotted if i.lineweight_mm < 0.13]
    if thin:
        plan.warnings.append("%d 条实体线宽 < 0.13mm（打印可能看不见）：%s"
                             % (len(thin), ", ".join(thin[:5])))
    wide = [i.handle for i in plotted if i.lineweight_mm > 2.0]
    if wide:
        plan.warnings.append("%d 条实体线宽 > 2.0mm（可能糊成一块）：%s"
                             % (len(wide), ", ".join(wide[:5])))
    return plan
