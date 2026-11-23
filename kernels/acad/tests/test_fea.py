"""FEA 流水线测试：网格质量 + 输入文件 + 求解结果与解析解对账。

需要 gmsh 与 ccx；缺哪个就跳过对应用例（不假装通过）。
"""

from __future__ import annotations

import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.fea import inp as I                                       # noqa: E402
from acadkit.fea import mesh as M                                     # noqa: E402
from acadkit.fea import runner as R                                   # noqa: E402

has_gmsh = M.gmsh_version() is not None
has_ccx = R.find_ccx() is not None


# ── 网格 ────────────────────────────────────────────────────────────
@pytest.mark.skipif(not has_gmsh, reason="没有 gmsh")
def test_box_mesh_quality_and_volume() -> None:
    mesh = M.box_mesh(10, 10, 100, mesh_size=10)
    s = mesh.summary()
    assert s["nodes"] > 10 and s["tets"] > 10
    assert s["inverted"] == 0, "不该有负体积四面体"
    assert abs(s["volume"] - 10 * 10 * 100) < 1e-6 * 10000, s["volume"]
    b = s["bbox"]
    assert abs(b["xmin"]) < 1e-9 and abs(b["xmax"] - 10) < 1e-9
    assert abs(b["zmax"] - 100) < 1e-9


@pytest.mark.skipif(not has_gmsh, reason="没有 gmsh")
def test_mesh_select_faces() -> None:
    mesh = M.box_mesh(10, 10, 100, mesh_size=12)
    tol = 1e-6
    fixed = mesh.select(lambda p: p[2] <= tol)
    loaded = mesh.select(lambda p: p[2] >= 100 - tol)
    assert fixed and loaded and not (set(fixed) & set(loaded))
    for n in loaded:
        assert abs(mesh.nodes[n][2] - 100) < 1e-6


@pytest.mark.skipif(not has_gmsh, reason="没有 gmsh")
def test_mesh_rejects_bad_size() -> None:
    try:
        M.box_mesh(10, 10, 10, mesh_size=0)
    except M.FeaError as exc:
        assert "正数" in str(exc)
    else:
        raise AssertionError("mesh_size=0 应报错")


# ── 输入文件 ────────────────────────────────────────────────────────
def _tiny_mesh() -> M.TetMesh:
    # 一个单位四面体，手算可控
    nodes = {1: (0.0, 0.0, 0.0), 2: (1.0, 0.0, 0.0),
             3: (0.0, 1.0, 0.0), 4: (0.0, 0.0, 1.0)}
    return M.TetMesh(nodes=nodes, tets=[(1, 2, 3, 4)], source="unit tet")


def test_write_inp_contains_required_cards() -> None:
    d = tempfile.mkdtemp(prefix="inp_")
    path = os.path.join(d, "t.inp")
    info = I.write_inp(path, _tiny_mesh(), material=I.Material(E=1000, nu=0.0),
                       fixed_nodes=[1, 2, 3], load_nodes=[4],
                       load_vector=(0.0, 0.0, 100.0))
    text = open(path, encoding="ascii").read()
    for card in ("*NODE", "*ELEMENT, TYPE=C3D4", "*NSET, NSET=FIX",
                 "*NSET, NSET=LOAD", "*BOUNDARY", "*ELASTIC", "*SOLID SECTION",
                 "*STATIC", "*CLOAD", "*NODE PRINT", "*END STEP"):
        assert card in text, "缺关键字：%s" % card
    assert info["elements"] == 1 and info["force_total"] == 100.0


def test_write_inp_rejects_bad_inputs() -> None:
    d = tempfile.mkdtemp(prefix="inp2_")
    path = os.path.join(d, "t.inp")
    cases = [
        dict(material=I.Material(E=-1, nu=0.0), fixed_nodes=[1], load_nodes=[4],
             load_vector=(0, 0, 1)),
        dict(material=I.Material(E=1, nu=0.6), fixed_nodes=[1], load_nodes=[4],
             load_vector=(0, 0, 1)),
        dict(material=I.Material(), fixed_nodes=[], load_nodes=[4],
             load_vector=(0, 0, 1)),
        dict(material=I.Material(), fixed_nodes=[1], load_nodes=[],
             load_vector=(0, 0, 1)),
        dict(material=I.Material(), fixed_nodes=[1], load_nodes=[4],
             load_vector=(0, 0, 0)),
        dict(material=I.Material(), fixed_nodes=[99], load_nodes=[4],
             load_vector=(0, 0, 1)),
    ]
    for kw in cases:
        try:
            I.write_inp(path, _tiny_mesh(), **kw)
        except M.FeaError:
            continue
        raise AssertionError("应报错：%r" % (kw,))


def test_parse_dat_from_synthetic_file() -> None:
    d = tempfile.mkdtemp(prefix="dat_")
    path = os.path.join(d, "x.dat")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("""
 displacements (vx,vy,vz) for set LOAD and time  0.1000000E+01

         5  1.0E-16  2.0E-16  4.761905E-02
         6 -1.0E-16  2.0E-16  4.761905E-02

 forces (fx,fy,fz) for set FIX and time  0.1000000E+01

         1  0.0  0.0 -2500.0
""")
    blocks = I.parse_dat(path)
    disp = blocks["displacements"]["LOAD"]
    assert set(disp) == {5, 6}
    peak = I.max_component(disp, axis=2)
    assert peak["node"] == 5 and abs(peak["value"] - 0.04761905) < 1e-8
    react = I.sum_reaction(blocks["reactions"]["FIX"])
    assert react[2] == -2500.0


def test_parse_dat_missing_file_and_empty() -> None:
    try:
        I.parse_dat(os.path.join(tempfile.gettempdir(), "nope_zzz.dat"))
    except M.FeaError as exc:
        assert "不存在" in str(exc)
    else:
        raise AssertionError("缺文件应报错")

    d = tempfile.mkdtemp(prefix="dat2_")
    path = os.path.join(d, "empty.dat")
    open(path, "w").close()
    try:
        I.parse_dat(path)
    except M.FeaError as exc:
        assert "没有位移块" in str(exc)
    else:
        raise AssertionError("空结果应报错")


@pytest.mark.skipif(not has_gmsh, reason="没有 gmsh")
def test_surface_triangles_cover_face() -> None:
    mesh = M.box_mesh(10, 10, 100, mesh_size=6)
    tol = 1e-6
    tris = mesh.surface_triangles(lambda p: p[2] >= 100 - tol)
    assert len(tris) >= 2, "上表面至少要拆成 2 个三角形"
    area = sum(mesh.tri_area(t) for t in tris)
    assert abs(area - 10 * 10) < 1e-6 * 100, "表面三角形面积应与截面 100 mm² 一致，实测 %r" % area


@pytest.mark.skipif(not has_gmsh, reason="没有 gmsh")
def test_consistent_loads_sum_to_total() -> None:
    """一致节点载荷的合力必须等于外载（这是静力平衡的前提）。"""
    mesh = M.box_mesh(10, 10, 100, mesh_size=6)
    loads = R.consistent_nodal_loads(mesh, lambda p: p[2] >= 100 - 1e-6,
                                     (0.0, 0.0, 10000.0))
    fz = sum(v[2] for v in loads.values())
    assert abs(fz - 10000.0) < 1e-6 * 10000, fz
    assert abs(sum(v[0] for v in loads.values())) < 1e-9
    for n in loads:
        assert abs(mesh.nodes[n][2] - 100) < 1e-6, "载荷只该加在上表面节点"


def test_nset_wrapped_at_16_entries() -> None:
    """ccx 规定每行 ≤16 个条目；超过时必须换行，否则报 splitline 错。"""
    # 造 24 个真实节点（一个四面体体单元 + 若干净节点），只测 NSET 的换行
    nodes = {i: (float(i), 0.0, 0.0) for i in range(1, 25)}
    mesh = M.TetMesh(nodes=nodes, tets=[(1, 2, 3, 4)], source="nset-test")
    d = tempfile.mkdtemp(prefix="nset_")
    path = os.path.join(d, "t.inp")
    I.write_inp(path, mesh, material=I.Material(), fixed_nodes=list(nodes),
                load_nodes=[4], load_vector=(0, 0, 1))
    text = open(path, encoding="ascii").read().split("*NSET, NSET=FIX")[1].split("*")[0]
    data_lines = [ln for ln in text.splitlines() if ln.strip()]
    assert all(len([x for x in ln.split(",") if x.strip()]) <= 16 for ln in data_lines), data_lines
    assert len(data_lines) >= 2, "24 个节点应拆成至少 2 行"


# ── 三种工况（默认二阶）─────────────────────────────────────────────
@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
def test_cantilever_matches_beam_theory() -> None:
    from acadkit.fea import cases as C
    out = C.cantilever_beam(length=200, width=20, height=20, mesh_size=8,
                            E=210000, nu=0.3, force=100,
                            workdir=tempfile.mkdtemp(prefix="cz_"))
    assert out["stage"] == "done", out
    assert out["ok"], out
    assert out["relative_error"] <= 2e-3, out["relative_error"]


@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
def test_torsion_matches_saint_venant() -> None:
    from acadkit.fea import cases as C
    out = C.shaft_torsion(radius=10, length=300, mesh_size=8, E=210000, nu=0.3,
                          torque=50000, workdir=tempfile.mkdtemp(prefix="tz_"))
    assert out["stage"] == "done", out
    assert out["ok"], out
    assert out["relative_error"] <= 1e-2, out["relative_error"]


@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
def test_plate_matches_thin_plate_theory() -> None:
    from acadkit.fea import cases as C
    out = C.simply_supported_plate(side=100, thickness=4, mesh_size=3, E=210000,
                                   nu=0.3, pressure=0.01,
                                   workdir=tempfile.mkdtemp(prefix="pl_"))
    assert out["stage"] == "done", out
    assert out["ok"], out
    assert out["relative_error"] <= 5e-2, out["relative_error"]


@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
def test_linear_tets_are_too_stiff_for_bending() -> None:
    """留作对照：线性四面体弯曲偏刚（~16%），这就是默认要二阶的原因。"""
    from acadkit.fea import cases as C
    out = C.cantilever_beam(length=200, width=20, height=20, mesh_size=5,
                            E=210000, nu=0.3, force=100, order=1,
                            workdir=tempfile.mkdtemp(prefix="lin_"))
    assert out["stage"] == "done", out
    assert out["relative_error"] > 5e-2, out["relative_error"]
    assert abs(out["measured"]) < abs(out["expected"]), "线性四面体应偏刚（位移偏小）"


@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
def test_plate_rejects_too_few_layers() -> None:
    from acadkit.fea import cases as C
    try:
        C.simply_supported_plate(side=100, thickness=4, mesh_size=3.0, E=210000,
                                 nu=0.3, pressure=0.01, order=1,
                                 workdir=tempfile.mkdtemp(prefix="pl2_"))
    except M.FeaError as exc:
        assert "厚度方向" in str(exc)
    else:
        raise AssertionError("单层单元应被拒绝（order=1）")


# ── brep → STEP → 网格 → ccx 的桥 ──────────────────────────────────
def _has_bridge() -> bool:
    try:
        from acadkit.brep import parts  # noqa: F401
    except Exception:                                   # noqa: BLE001
        return False
    return has_gmsh and has_ccx


@pytest.mark.skipif(not _has_bridge(), reason="缺 cadquery/gmsh/ccx")
def test_part_mesh_volume_faithful_for_plate() -> None:
    from acadkit.brep import parts as B
    from acadkit.fea import brep_bridge as BB
    pm = BB.part_mesh(B.plate(length=200, width=100, thickness=8), mesh_size=4.0,
                      order=2, workdir=tempfile.mkdtemp(prefix="pm_"))
    assert pm.mesh.tets and len(pm.mesh.inverted()) == 0
    assert pm.volume_error < 1e-6, "直板体网格体积应与零件完全一致，实测 %.3e" % pm.volume_error
    assert BB.brep.read_step(pm.step_path)["solids"] == 1


@pytest.mark.skipif(not _has_bridge(), reason="缺 cadquery/gmsh/ccx")
def test_brep_shaft_axial_matches_analytic() -> None:
    from acadkit.brep import parts as B
    from acadkit.fea import brep_bridge as BB
    out = BB.axial_part(B.shaft(diameter=20, length=200), force=5000, E=210000,
                        nu=0.0, mesh_size=6.0, tol=3e-2,
                        workdir=tempfile.mkdtemp(prefix="bs_"))
    assert out["stage"] == "done", out
    assert out["ok"], out
    assert out["part"]["volume_error"] < 0.05
    assert out["slenderness"] > 3


@pytest.mark.skipif(not _has_bridge(), reason="缺 cadquery/gmsh/ccx")
def test_brep_plate_cantilever_matches_beam_within_plate_effect() -> None:
    from acadkit.brep import parts as B
    from acadkit.fea import brep_bridge as BB
    out = BB.cantilever_part(B.plate(length=200, width=100, thickness=8), force=100,
                             E=210000, nu=0.3, mesh_size=6.0, axis="x", load_axis="z",
                             workdir=tempfile.mkdtemp(prefix="bc_"))
    assert out["stage"] == "done", out
    assert out["ok"], out
    assert abs(out["measured"]) < abs(out["expected"]), "宽板受反平面约束应比梁理论更刚"


@pytest.mark.skipif(not _has_bridge(), reason="缺 cadquery/gmsh/ccx")
def test_brep_refuses_bar_theory_for_wide_part() -> None:
    """法兰 L/√A≈0.10，一维杆公式不适用——必须拒绝，而不是给个 63% 错的数。"""
    from acadkit.brep import parts as B
    from acadkit.fea import brep_bridge as BB
    flange = B.flange(outer_d=120, bore_d=40, thickness=10,
                      bolt_holes=[{"diameter": 10, "bcd": 64, "count": 4}])
    try:
        BB.axial_part(flange, force=10000, E=210000, nu=0.3, mesh_size=5.0,
                      workdir=tempfile.mkdtemp(prefix="bf_"))
    except M.FeaError as exc:
        assert "细长比" in str(exc)
        assert "不适用" in str(exc)
    else:
        raise AssertionError("宽扁件应拒绝一维杆公式")


@pytest.mark.skipif(not _has_bridge(), reason="缺 cadquery/gmsh/ccx")
def test_brep_refuses_unfaithful_mesh() -> None:
    """粗网格下圆柱体积少 >5% → 拒算（否则算的不是这个件）。"""
    from acadkit.brep import parts as B
    from acadkit.fea import brep_bridge as BB
    try:
        BB.part_mesh(B.shaft(diameter=20, length=200), mesh_size=15.0, order=2,
                     workdir=tempfile.mkdtemp(prefix="bfm_"))
    except M.FeaError as exc:
        assert "体积" in str(exc) and "拒算" in str(exc)
    else:
        raise AssertionError("网格不忠实应拒算")


@pytest.mark.skipif(not _has_bridge(), reason="缺 cadquery/gmsh/ccx")
def test_brep_refuses_short_cantilever() -> None:
    from acadkit.brep import parts as B
    from acadkit.fea import brep_bridge as BB
    try:
        BB.cantilever_part(B.plate(length=30, width=100, thickness=8), force=100,
                           E=210000, nu=0.3, mesh_size=4.0, axis="x", load_axis="z",
                           workdir=tempfile.mkdtemp(prefix="bsc_"))
    except M.FeaError as exc:
        assert "长厚比" in str(exc)
    else:
        raise AssertionError("L/h<5 应拒绝梁理论")


# ── 求解器定位 ──────────────────────────────────────────────────────
def test_find_ccx_or_none() -> None:
    got = R.find_ccx()
    if got:
        assert os.path.isfile(got)
    else:
        pytest.skip("本机没有 ccx")


def test_run_rejects_missing_inp() -> None:
    try:
        R.run(os.path.join(tempfile.gettempdir(), "no_such_job_zzz.inp"))
    except M.FeaError as exc:
        assert "不存在" in str(exc)
    else:
        raise AssertionError("缺输入应报错")


# ── 端到端：与解析解对账 ────────────────────────────────────────────
@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
def test_axial_bar_nu0_matches_analytic() -> None:
    """ν=0 时一维杆解精确：uz = FL/(EA)。这是整条链路的判据。"""
    d = tempfile.mkdtemp(prefix="fea_bar_")
    out = R.solve_bar(length=100, width=10, height=10, mesh_size=20,
                      E=210000, nu=0.0, total_force=10000, workdir=d)
    assert out["ok"], out
    assert out["mesh"]["inverted"] == 0
    assert out["relative_error"] <= 1e-6, out["relative_error"]


@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
@pytest.mark.parametrize("mesh_size", [10, 6, 4])
def test_axial_bar_exact_at_any_mesh_density(mesh_size: int) -> None:
    """一致载荷下线性四面体对均匀拉伸是精确的——加密不应改变答案。"""
    d = tempfile.mkdtemp(prefix="fea_exact_")
    out = R.solve_bar(length=100, width=10, height=10, mesh_size=mesh_size,
                      E=210000, nu=0.0, total_force=10000, workdir=d)
    assert out["ok"], out
    assert out["relative_error"] <= 1e-6, "h=%d 时误差 %.3e" % (mesh_size, out["relative_error"])


@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
def test_axial_bar_poisson_effect_is_physical() -> None:
    """ν=0.3 时固定端限制横向收缩 → 实测位移应略小于一维理论（不是错，是约束效应）。"""
    d = tempfile.mkdtemp(prefix="fea_bar2_")
    out = R.solve_bar(length=100, width=10, height=10, mesh_size=20,
                      E=210000, nu=0.3, total_force=10000, workdir=d)
    # ν≠0 时**不该**要求与一维理论一致（固定端限制横向收缩），只要求解出来了
    assert out["stage"] == "done", out
    rel = out["relative_error"]
    assert 0.0 < rel < 0.15, "偏差应在 15%% 内，实测 %.3f%%" % (rel * 100)
    assert abs(out["measured_uz"]) < abs(out["expected_uz"]), "约束端会让件更刚"


@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
def test_cylinder_axial_matches_analytic() -> None:
    """圆截面：按网格有效面积对账，离散误差应在 0.2% 内。"""
    d = tempfile.mkdtemp(prefix="fea_cyl_")
    out = R.solve_cylinder(radius=10, length=300, mesh_size=5, E=210000, nu=0.0,
                           total_force=5000, workdir=d)
    assert out["stage"] == "done", out
    assert out["ok"], out
    assert out["relative_error"] <= 2e-3, out["relative_error"]
    # 内接多面体的面积误差随网格加密下降（h=5 实测 3.2%），这里只兜住量级
    assert out["area_error"] < 0.05, "面积误差应在 5%% 内，实测 %.4f" % out["area_error"]


@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
def test_cylinder_error_refines_toward_zero() -> None:
    """加密网格误差必须下降（证明残差是离散误差，不是系统性 bug）。"""
    coarse = R.solve_cylinder(radius=10, length=300, mesh_size=8, E=210000, nu=0.0,
                              total_force=5000, workdir=tempfile.mkdtemp(prefix="cyl_a_"))
    fine = R.solve_cylinder(radius=10, length=300, mesh_size=3.5, E=210000, nu=0.0,
                            total_force=5000, workdir=tempfile.mkdtemp(prefix="cyl_b_"))
    assert coarse["stage"] == fine["stage"] == "done"
    assert fine["relative_error"] < coarse["relative_error"], (
        "粗 %e 应大于细 %e" % (coarse["relative_error"], fine["relative_error"]))


@pytest.mark.skipif(not (has_gmsh and has_ccx), reason="缺 gmsh 或 ccx")
def test_reaction_balances_applied_load() -> None:
    """反力合力应与外载平衡（静力最基本的一致性）。"""
    d = tempfile.mkdtemp(prefix="fea_react_")
    out = R.solve_bar(length=100, width=10, height=10, mesh_size=20,
                      E=210000, nu=0.0, total_force=10000, workdir=d)
    assert out["ok"], out
    blocks = I.parse_dat(out["dat"])
    react = I.sum_reaction(blocks["reactions"]["FIX"])
    assert abs(react[2] + 10000.0) < 1.0, "Z 向反力应 ≈ -10000，实测 %r" % (react,)
    assert abs(react[0]) < 1.0 and abs(react[1]) < 1.0
