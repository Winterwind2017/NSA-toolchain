"""
非标直线/旋转传动方案推荐

先选路线，再交给 ballscrew / motor / reducer 做校核。
"""

from __future__ import annotations


def recommend_drive(
    motion: str,
    stroke_mm: float = 0.0,
    speed_mm_s: float = 0.0,
    repeatability_mm: float = 0.05,
    load_kg: float = 5.0,
    vertical: bool = False,
    dirty: bool = False,
    stations: int = 1,
    cycle_fixed: bool = False,
) -> dict:
    """
    推荐传动路线。

    Args:
        motion: 'linear' 或 'rotary'
        stroke_mm: 直线行程 mm；旋转可忽略
        speed_mm_s: 直线速度 mm/s；旋转时当作切向速度量级
        repeatability_mm: 重复定位 mm（旋转时把角精度换算到作用半径）
        load_kg: 运动部分质量 kg
        vertical: 是否垂直
        dirty: 粉尘/油污重
        stations: 旋转分度工位数
        cycle_fixed: 节拍/工位几乎不变（分割器才合适）
    """
    notes: list[str] = []
    if vertical:
        notes.append("垂直轴必须有刹车或自锁，断电不能溜车")

    if motion == "rotary":
        if stations >= 4 and cycle_fixed and repeatability_mm >= 0.05:
            drive = "凸轮分割器"
            reason = "固定工位间歇分度，分割段机械锁死"
        elif repeatability_mm <= 0.02:
            drive = "DD马达或伺服+谐波/行星"
            reason = "连续或柔性转位、精度高"
        else:
            drive = "伺服+行星减速机"
            reason = "通用旋转轴"
        if not cycle_fixed and "分割器" in drive:
            notes.append("工位或节拍常改时不要用分割器")
        return {"drive": drive, "reason": reason, "notes": notes}

    # linear
    if stroke_mm <= 0:
        raise ValueError("直线轴需要 stroke_mm")

    precise = repeatability_mm <= 0.03
    long = stroke_mm >= 800
    fast = speed_mm_s >= 1000
    heavy = load_kg >= 40

    if precise and not long and not fast:
        drive = "伺服+滚珠丝杆"
        reason = "短中行程、高精度、可出力"
        if vertical:
            notes.append("导程勿过大，配电机抱闸")
    elif long and precise and heavy:
        drive = "伺服+齿轮齿条（消隙）"
        reason = "长行程还要定位和承载"
        notes.append("齿条拼接+润滑+与导轨平行度")
        if dirty:
            notes.append("敞开齿条易进灰，加护罩")
    elif fast or (long and not precise):
        drive = "伺服+同步带"
        reason = "高速或长行程中等精度"
        notes.append("必须张紧；垂直轴必须抱闸")
        if dirty:
            notes.append("油污粉尘会掉齿，改防护或换链条做输送")
    elif not precise and (heavy or dirty):
        drive = "链条（定位另做挡停/凸轮）"
        reason = "重载输送，不靠链条本身定位"
    else:
        drive = "伺服+滚珠丝杆"
        reason = "默认精密直线轴"

    if stroke_mm >= 2000 and "丝杆" in drive:
        notes.append("超长丝杆优先改齿条或同步带")

    return {"drive": drive, "reason": reason, "notes": notes}
