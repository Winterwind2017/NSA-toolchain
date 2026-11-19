"""动态块 / 就地编辑 / 出图管线的离线测试。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.model.dyngrip import (DynBlockError, DynamicBlock, Grip,      # noqa: E402
                                   Parameter, VisibilityState)
from acadkit.model.plotplan import (BYLAYER, EntityStyle, LayerStyle,      # noqa: E402
                                    PlotPlanError, build_plan, resolve)
from acadkit.model.refedit import RefEditError, RefEditSession             # noqa: E402


# ── 动态块 ──────────────────────────────────────────────────────────
def _block() -> DynamicBlock:
    b = DynamicBlock("Door")
    b.parameters["Width"] = Parameter("Width", "linear", 900, 600, 1200)
    b.parameters["Angle"] = Parameter("Angle", "rotation", 0)
    b.states["Closed"] = VisibilityState("Closed", {"A", "B"})
    b.states["Open"] = VisibilityState("Open", {"A"})
    b.grips = [Grip((0.0, 0.0), "Width"), Grip((100.0, 0.0), "Angle")]
    return b


def test_parameter_validation() -> None:
    b = _block()
    assert b.set_value("Width", 1000) == 1000
    for bad in (500, 1300):
        try:
            b.set_value("Width", bad)
        except DynBlockError as exc:
            assert "上限" in str(exc) or "下限" in str(exc)
        else:
            raise AssertionError("越界应报错：%r" % bad)
    try:
        b.set_value("Nope", 1)
    except DynBlockError as exc:
        assert "没有参数" in str(exc)
    else:
        raise AssertionError("未知参数应报错")


def test_unknown_parameter_kind_rejected() -> None:
    try:
        Parameter("X", "teleport")
    except DynBlockError as exc:
        assert "未知参数类型" in str(exc)
    else:
        raise AssertionError("未知类型应报错")


def test_visibility_switch_reports_show_hide() -> None:
    b = _block()
    diff = b.switch_visibility("Open")
    assert diff["hide"] == ["B"] and diff["show"] == [] and diff["kept"] == ["A"]
    diff2 = b.switch_visibility("Closed")
    assert diff2["show"] == ["B"]


def test_visibility_unknown_state() -> None:
    try:
        _block().visible_entities("Nope")
    except DynBlockError as exc:
        assert "没有可见性状态" in str(exc)
    else:
        raise AssertionError("未知状态应报错")


def test_grip_points_follow_parameters() -> None:
    b = _block()
    b.set_value("Width", 700)          # 参数下限 600，用合法值
    pts = b.grip_points()
    assert pts[0]["point"] == (700.0, 0.0), pts[0]
    b.set_value("Angle", 45)
    pts2 = b.grip_points()                 # 参数变了要重算
    assert pts2[1]["angle_deg"] == 45


def test_summary_counts() -> None:
    s = _block().summary()
    assert s["name"] == "Door" and s["states"] == {"Closed": 2, "Open": 1}


# ── 就地编辑 ────────────────────────────────────────────────────────
def test_cannot_modify_before_begin() -> None:
    sess = RefEditSession("B1", {"a": 1})
    try:
        sess.modify("a", 2)
    except RefEditError as exc:
        assert "不在编辑中" in str(exc)
    else:
        raise AssertionError("未开始编辑不该能改")


def test_changes_are_recorded_and_committed() -> None:
    sess = RefEditSession("B1", {"a": 1, "b": 2}).begin()
    sess.modify("a", 10)
    sess.add("c", 3)
    sess.delete("b")
    out = sess.commit()
    assert out["changes"] == 3 and out["content"] == {"a": 10, "c": 3}
    assert sess.state == "committed"


def test_abort_restores_original() -> None:
    original = {"a": 1, "b": {"nested": [1, 2]}}
    sess = RefEditSession("B1", original).begin()
    sess.modify("a", 99)
    sess.modify("b", {"nested": []})
    sess.abort()
    assert sess.verify_restored(original), "放弃必须逐键还原（含嵌套）"
    assert sess.changes == []


def test_double_commit_and_double_abort_rejected() -> None:
    sess = RefEditSession("B1", {"a": 1}).begin()
    sess.commit()
    for fn in (sess.commit, sess.abort):
        try:
            fn()
        except RefEditError:
            continue
        raise AssertionError("重复收尾应报错")


def test_missing_target_errors() -> None:
    sess = RefEditSession("B1", {"a": 1}).begin()
    cases = [(lambda: sess.modify("zz", 1), "改不存在的"),
             (lambda: sess.delete("zz"), "删不存在的"),
             (lambda: sess.add("a", 1), "加已存在的")]
    for fn, why in cases:
        try:
            fn()
        except RefEditError:
            continue
        raise AssertionError("%s 应报错" % why)


# ── 出图管线 ────────────────────────────────────────────────────────
def _layers() -> dict:
    return {"OUTLINE": LayerStyle("OUTLINE", lineweight=50, color=7),
            "HIDDEN": LayerStyle("HIDDEN", lineweight=13, color=8),
            "NOTE": LayerStyle("NOTE", lineweight=BYLAYER, color=2, plottable=False)}


def test_bylayer_inherits() -> None:
    r = resolve(EntityStyle("1", "OUTLINE"), _layers())
    assert r.lineweight_mm == 0.5 and r.source["lineweight"] == "layer"
    assert r.color == 7


def test_entity_override_wins() -> None:
    r = resolve(EntityStyle("2", "OUTLINE", lineweight=100), _layers())
    assert r.lineweight_mm == 1.0 and r.source["lineweight"] == "entity"


def test_bylayer_layer_is_default() -> None:
    r = resolve(EntityStyle("3", "NOTE"), _layers(), default_lw=25)
    assert r.lineweight_mm == 0.25 and r.source["lineweight"] == "default"


def test_unknown_layer_raises() -> None:
    try:
        resolve(EntityStyle("4", "GHOST"), _layers())
    except PlotPlanError as exc:
        assert "不存在的图层" in str(exc)
    else:
        raise AssertionError("未知图层应报错")


def test_invalid_lineweight_rejected() -> None:
    try:
        resolve(EntityStyle("5", "OUTLINE", lineweight=12345), _layers())
    except PlotPlanError as exc:
        assert "非法线宽" in str(exc)
    else:
        raise AssertionError("非法线宽应报错")


def test_plan_histogram_and_omitted() -> None:
    ents = [EntityStyle("1", "OUTLINE"), EntityStyle("2", "OUTLINE"),
            EntityStyle("3", "HIDDEN"), EntityStyle("4", "NOTE")]
    plan = build_plan(ents, _layers())
    assert plan.lineweight_histogram() == {0.13: 1, 0.5: 2}
    assert plan.omitted == ["4"]


def test_plan_warns_uniform_lineweight() -> None:
    ents = [EntityStyle(str(i), "OUTLINE") for i in range(3)]
    plan = build_plan(ents, _layers())
    assert any("所有实体线宽" in w for w in plan.warnings)


def test_plan_warns_too_thin() -> None:
    ents = [EntityStyle("1", "THIN"), EntityStyle("2", "OUTLINE")]
    layers = _layers()
    layers["THIN"] = LayerStyle("THIN", lineweight=5)      # 0.05mm
    plan = build_plan(ents, layers)
    assert any("0.13mm" in w for w in plan.warnings)


def test_plan_empty() -> None:
    plan = build_plan([], _layers())
    assert plan.warnings and "没有任何可出图实体" in plan.warnings[0]
