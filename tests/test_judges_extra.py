"""新增判据的离线测试：每条都要能**失败**（JUDGE_SPEC 第四节）。"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acadkit import caps as capsmod                       # noqa: E402
from acadkit import fit as fitmod                         # noqa: E402
from acadkit.judges import env as j_env                   # noqa: E402
from acadkit.judges import frame as j_frame               # noqa: E402
from acadkit.judges import generic as j_g                # noqa: E402
from acadkit.judges import layer as j_layer               # noqa: E402
from acadkit.judges import solid as j_solid               # noqa: E402
from acadkit.judges import symbol as j_sym                # noqa: E402
from acadkit.judges import view as j_view                 # noqa: E402
from acadkit.judges.base import Drawing, Entity, Readback, value_same  # noqa: E402
from acadkit.judges.fit import judge_fit_code             # noqa: E402


def E(handle, type_name, **attrs):
    return Entity(handle=handle, type=type_name, attrs=dict(attrs))


def D(source, entities, meta=None):
    return Drawing(source=source, insunits=4, entities=list(entities),
                   meta=meta or {})


def RB(before, memory, reopened=None):
    return Readback(before=before, memory=memory, reopened=reopened)


# ── value_same：字符串/点列/数都要能比 ─────────────────────────────
def test_value_same_handles_strings_points_and_nested() -> None:
    assert value_same("ANSI31", "ANSI31")
    assert not value_same("ANSI31", "ANSI32")
    assert value_same((0, 0, 0), (0, 0, 0))
    assert value_same([[(0, 0), (1, 1)]], [[(0, 0), (1, 1)]])
    assert not value_same([[(0, 0)]], [[(0, 1)]])
    assert value_same(True, 1)
    assert not value_same(60.0, 61.0)


# ── 通用实体判据 ───────────────────────────────────────────────────
def test_judge_new_entity_positive_and_negative() -> None:
    arc = E("A1", "ARC", ObjectName="AcDbArc", Center=[0.0, 0.0, 0.0],
            Radius=10.0, StartAngle=0.0, EndAngle=math.pi / 2)
    ok = j_g.judge_new_entity(
        RB(D("b", []), D("m", [arc]), D("r", [arc])),
        type_name="ARC", object_name="AcDbArc",
        expected={"Center": (0, 0, 0), "Radius": 10.0})
    assert ok["ok"] is True
    bad = j_g.judge_new_entity(
        RB(D("b", []), D("m", [arc]), D("r", [arc])),
        type_name="ARC", object_name="AcDbArc",
        expected={"Center": (0, 0, 0), "Radius": 11.0})
    assert bad["ok"] is False and bad["checks"]["attr:Radius"] is False


def test_judge_new_entity_requires_unique_new_entity() -> None:
    a = E("A1", "LINE", ObjectName="AcDbLine", StartPoint=[0, 0, 0],
          EndPoint=[1, 0, 0], Length=1.0)
    b = E("A2", "LINE", ObjectName="AcDbLine", StartPoint=[0, 1, 0],
          EndPoint=[1, 1, 0], Length=1.0)
    res = j_g.judge_new_entity(RB(D("b", []), D("m", [a, b])),
                               type_name="LINE", object_name="AcDbLine")
    assert res["ok"] is False and res["checks"]["count"] is False


def test_judge_delta_and_contains() -> None:
    t = E("T1", "TEXT", ObjectName="AcDbText", TextString="Ra 3.2")
    ok = j_g.judge_delta(RB(D("b", []), D("m", [t]), D("r", [t])),
                         expect={"TEXT": 1},
                         attrs=[{"type": "TEXT",
                                 "expected": {"TextString": "Ra 3.2"}}])
    assert ok["ok"] is True
    bad = j_g.judge_delta(RB(D("b", []), D("m", [t])),
                          expect={"TEXT": 2})
    assert bad["ok"] is False and bad["checks"]["count:TEXT"] is False


def test_judge_named_table_positive_negative() -> None:
    before = D("b", [], meta={"tables": {"layers": {}}})
    mem = D("m", [], meta={"tables": {"layers": {"01_OUT": {"Color": 3}}}})
    re = D("r", [], meta={"tables": {"layers": {"01_OUT": {"Color": 3}}}})
    ok = j_g.judge_named_table(RB(before, mem, re), table="layers",
                               name="01_OUT", expected={"Color": 3})
    assert ok["ok"] is True
    bad = j_g.judge_named_table(RB(before, mem, re), table="layers",
                                name="01_OUT", expected={"Color": 4})
    assert bad["ok"] is False and bad["checks"]["attr:Color"] is False


def test_judge_contains_check() -> None:
    st = E("S1", "TEXTSTYLE", ObjectName="AcDbTextStyleTableRecord",
           FontFile="SimSun.ttf")
    mem = D("m", [], meta={"tables": {"textstyles": {"CN": st.attrs}}})
    res = j_g.judge_named_table(RB(D("b", []), mem, mem), table="textstyles",
                                name="CN", contains={"FontFile": "SimSun"})
    assert res["checks"]["contains:FontFile"] is True


# ── 体积 / 布尔 ────────────────────────────────────────────────────
def test_judge_solids_matches_volumes() -> None:
    s1 = E("S1", "3DSOLID", ObjectName="AcDb3dSolid", Volume=8000.0)
    s2 = E("S2", "3DSOLID", ObjectName="AcDb3dSolid", Volume=6283.185)
    ok = j_solid.judge_solids(RB(D("b", []), D("m", [s1, s2]), D("r", [s1, s2])),
                              expected=[8000.0, 6283.185])
    assert ok["ok"] is True
    bad = j_solid.judge_solids(RB(D("b", []), D("m", [s1, s2])),
                               expected=[8000.0, 6000.0])
    assert bad["ok"] is False


def test_judge_boolean_needs_two_to_one_and_volume() -> None:
    one = E("S1", "3DSOLID", ObjectName="AcDb3dSolid", Volume=10000.0)
    ok = j_solid.judge_boolean(RB(D("b", []), D("m", [one]), D("r", [one])),
                               expected_volume=10000.0)
    assert ok["ok"] is True
    bad = j_solid.judge_boolean(RB(D("b", []), D("m", [one])),
                                expected_volume=12000.0)
    assert bad["ok"] is False and bad["checks"]["volume"] is False


def test_judge_slice_sums_pieces() -> None:
    p1 = E("P1", "3DSOLID", ObjectName="AcDb3dSolid", Volume=4000.0)
    p2 = E("P2", "3DSOLID", ObjectName="AcDb3dSolid", Volume=4000.0)
    ok = j_solid.judge_slice(RB(D("b", []), D("m", [p1, p2])), expected_total=8000.0)
    assert ok["ok"] is True
    bad = j_solid.judge_slice(RB(D("b", []), D("m", [p1])), expected_total=8000.0)
    assert bad["ok"] is False


# ── 配合代号：独立表值 ─────────────────────────────────────────────
def test_fit_code_reference_values() -> None:
    assert fitmod.fit_deviation("H7", 50) == (0.025, 0.0)
    assert fitmod.fit_deviation("h6", 50) == (0.0, -0.016)
    assert fitmod.fit_deviation("f7", 25) == (-0.020, -0.041)
    res = judge_fit_code()
    assert res["ok"] is True
    assert all(res["checks"].values())


def test_fit_code_breaks_when_table_is_wrong(monkeypatch) -> None:
    bad = (("H7", 50.0, 0.999, 0.0),)
    res = judge_fit_code(reference=bad)
    assert res["ok"] is False and res["checks"]["fit:H7@50"] is False


def test_fit_code_out_of_range_raises() -> None:
    try:
        fitmod.fit_deviation("H7", 600)
    except ValueError as exc:
        assert "500" in str(exc)
    else:                                            # pragma: no cover
        raise AssertionError("超范围必须抛错")


# ── 图层 / 环境 / 视图 / 图框 ──────────────────────────────────────
def test_layer_snapshot_positive_and_negative() -> None:
    layer = {"04_SNAP": {"Color": 6, "Freeze": False}}
    mem = D("m", [], meta={"tables": {"layers": layer}})
    re = D("r", [], meta={"tables": {"layers": layer}})
    recorded = {"name": "04_SNAP", "snapshot": layer,
                "mutated": {"04_SNAP": {"Color": 1, "Freeze": True}},
                "changed": {"04_SNAP": {"Color": 1, "Freeze": True}}}
    ok = j_layer.judge_layer_snapshot(RB(D("b", []), mem, re), recorded=recorded)
    assert ok["ok"] is True
    broken = {"04_SNAP": {"Color": 1, "Freeze": True}}
    mem2 = D("m", [], meta={"tables": {"layers": broken}})
    re2 = D("r", [], meta={"tables": {"layers": broken}})
    bad = j_layer.judge_layer_snapshot(RB(D("b", []), mem2, re2),
                                       recorded=recorded)
    assert bad["ok"] is False


def test_layer_snapshot_mutation_not_observed_fails() -> None:
    layer = {"04_SNAP": {"Color": 6, "Freeze": False}}
    mem = D("m", [], meta={"tables": {"layers": layer}})
    recorded = {"snapshot": layer,
                "mutated": {"04_SNAP": {"Color": 1}},
                "changed": {"04_SNAP": {"Color": 6}}}   # 没改成
    res = j_layer.judge_layer_snapshot(RB(D("b", []), mem, mem),
                                       recorded=recorded)
    assert res["ok"] is False


def test_judge_sysvar_set_and_restore() -> None:
    ok = j_env.judge_sysvar({"before": 2.5, "after": 3.5, "restored": 2.5},
                            name="DIMTXT", expected=3.5)
    assert ok["ok"] is True
    bad = j_env.judge_sysvar({"before": 2.5, "after": 2.5, "restored": 2.5},
                             name="DIMTXT", expected=3.5)
    assert bad["ok"] is False and bad["checks"]["changed"] is False


def test_judge_zoom_covers_geometry() -> None:
    meta = {"view": {"center": [500.0, 500.0], "size": 220.0}}
    ok = j_view.judge_zoom(RB(D("b", []), D("m", [], meta=meta)),
                           center=(500.0, 500.0), radius=100.0)
    assert ok["ok"] is True
    meta2 = {"view": {"center": [0.0, 0.0], "size": 50.0}}
    bad = j_view.judge_zoom(RB(D("b", []), D("m", [], meta=meta2)),
                            center=(500.0, 500.0), radius=100.0)
    assert bad["ok"] is False


def test_judge_layout_viewport_delta() -> None:
    tables = {"layouts": {"SHEET_A": {}}, "layout_viewports": {"SHEET_A": 2}}
    mem = D("m", [], meta={"tables": tables})
    ok = j_frame.judge_layout(RB(D("b", []), mem, mem), name="SHEET_A",
                              recorded={"viewports_before": 1,
                                        "viewports_after": 2})
    assert ok["ok"] is True
    bad = j_frame.judge_layout(RB(D("b", []), mem),
                               name="SHEET_A",
                               recorded={"viewports_before": 2,
                                         "viewports_after": 2})
    assert bad["ok"] is False and bad["checks"]["viewport_added"] is False


def test_judge_centermark_needs_lines_through_center() -> None:
    l1 = E("L1", "LINE", ObjectName="AcDbLine", StartPoint=[-11, 0, 0],
           EndPoint=[11, 0, 0], Length=22.0)
    l2 = E("L2", "LINE", ObjectName="AcDbLine", StartPoint=[0, -11, 0],
           EndPoint=[0, 11, 0], Length=22.0)
    ok = j_sym.judge_centermark(RB(D("b", []), D("m", [l1, l2]),
                                   D("r", [l1, l2])),
                                center=(0, 0), arm=11.0)
    assert ok["ok"] is True
    l3 = E("L3", "LINE", ObjectName="AcDbLine", StartPoint=[5, 0, 0],
           EndPoint=[27, 0, 0], Length=22.0)
    bad = j_sym.judge_centermark(RB(D("b", []), D("m", [l1, l3])),
                                 center=(0, 0), arm=11.0)
    assert bad["ok"] is False and bad["checks"]["through_center"] is False


# ── caps 与判据的接线 ──────────────────────────────────────────────
def test_caps_judges_are_callable_with_params() -> None:
    for cap in capsmod.CAPS:
        assert callable(cap.judge)
        assert isinstance(cap.params, dict)


def test_every_family_has_at_least_one_case() -> None:
    for fam, ids in capsmod.FAMILIES.items():
        assert ids, fam
        assert all(i in capsmod.BY_ID for i in ids)
