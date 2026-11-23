"""出图测试：零件图 / 三视图 / 线框 SVG / FEA 变形云图。

判据都是可复算的：PNG 魔数、字节数、像素标准差（空白图会趋 0）、
视角互不相同、SVG 路径数与隐藏线标记。
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.fea import mesh as M                                # noqa: E402
from acadkit.fea import runner as R                              # noqa: E402
from acadkit.fea import view as V                                # noqa: E402

try:
    from acadkit.brep import parts as B
    from acadkit.brep import render as R2
    has_brep = True
except Exception:                                     # noqa: BLE001
    has_brep = False

try:
    import pyvista                                  # noqa: F401
    has_pv = True
except Exception:                                     # noqa: BLE001
    has_pv = False

need = pytest.mark.skipif(not (has_brep and has_pv),
                          reason="缺 cadquery/pyvista")


def _tmp() -> str:
    return tempfile.mkdtemp(prefix="vis_")


# ── 零件图 ────────────────────────────────────────────────────────
@need
def test_iso_png_is_real_and_not_blank() -> None:
    d = _tmp()
    path = os.path.join(d, "iso.png")
    st = R2.iso_png(B.plate(length=120, width=80, thickness=10), path)
    assert st["bytes"] > 3000, st
    assert st["size"] == [900, 650]
    assert st["pixel_std"] > 2.0, "空白图的像素标准差会趋 0"
    assert open(path, "rb").read(8) == b"\x89PNG\r\n\x1a\n"


@need
def test_three_view_has_three_panels_and_differs_by_view() -> None:
    d = _tmp()
    part = B.flange(outer_d=120, bore_d=40, thickness=10,
                    bolt_holes=[{"diameter": 10, "bcd": 90, "count": 4}])
    st = R2.three_view_png(part, os.path.join(d, "three.png"))
    assert st["views"] == ["front", "top", "right"]
    assert st["size"][0] >= 1000, "三视图应横向拼接"
    assert st["bytes"] > 5000

    a = R2.three_view_png(part, os.path.join(d, "front_only.png"), views=("front",))
    b = R2.three_view_png(part, os.path.join(d, "top_only.png"), views=("top",))
    assert a["bytes"] != b["bytes"], "不同视角的画面不应完全相同"


@need
def test_svg_has_paths_and_hidden_lines() -> None:
    d = _tmp()
    path = os.path.join(d, "wire.svg")
    st = R2.svg_views(B.flange(outer_d=120, bore_d=40, thickness=10,
                              bolt_holes=[{"diameter": 10, "bcd": 90, "count": 4}]), path)
    assert st["paths"] >= 5, st
    assert st["bytes"] > 1000
    assert st["has_hidden"] is True, "带内孔/槽的件应有隐藏线（stroke-dasharray）"


@need
def test_render_rejects_bad_input() -> None:
    d = _tmp()
    part = B.plate(length=100, width=60, thickness=8)
    for call in (lambda: R2.iso_png(object(), os.path.join(d, "x.png")),
                 lambda: R2.three_view_png(part, os.path.join(d, "y.png"), views=()),
                 lambda: R2.iso_png(part, os.path.join(d, "no_such_dir", "z.png")),
                 lambda: R2.polydata(part, tolerance=0.0)):
        try:
            call()
        except Exception as exc:                      # noqa: BLE001
            assert "BrepError" in type(exc).__name__ or hasattr(exc, "args")
        else:
            raise AssertionError("非法出图输入应报错")


# ── FEA 云图 ──────────────────────────────────────────────────────
def test_boundary_triangles_are_only_surface() -> None:
    mesh = M.box_mesh(10, 10, 10, mesh_size=5)
    bnd = V.boundary_triangles(mesh)
    total = 4 * len(mesh.tets)
    assert 0 < len(bnd) < total, "边界面必须少于全部面（说明内部面被排除了）"
    assert len(bnd) == len(set(bnd)), "边界三角形不应重复"


def test_auto_scale_grows_when_disp_shrinks() -> None:
    import numpy as np
    mesh = M.box_mesh(20, 10, 10, mesh_size=10)
    big = np.full((len(mesh.nodes), 3), 1e-2)
    small = np.full((len(mesh.nodes), 3), 1e-4)
    assert V.auto_scale(mesh, small) > V.auto_scale(mesh, big)


@need
def test_deformed_png_from_fea_result() -> None:
    from acadkit.fea import brep_bridge as BB
    d = _tmp()
    out = BB.cantilever_part(B.plate(length=200, width=100, thickness=8), force=100,
                             E=210000, nu=0.3, mesh_size=6.0, axis="x", load_axis="z",
                             workdir=_tmp())
    st = V.deformed_from_result(out, os.path.join(d, "warp.png"))
    assert st["bytes"] > 3000
    assert st["triangles"] > 100, "边界三角形太少，网格可能有问题"
    assert st["max_disp"] > 0
    assert st["scale"] > 0
    assert st["missing_nodes"] == 0, "MEASURE 集合应覆盖被打印节点"
    assert st["color_spread"] > 10, "云图应有颜色分布，而不是单色块"


@need
def test_cli_png_written_for_every_solving_branch() -> None:
    """--png 不能在某些分支被静默忽略：bracket / stepped 都走各自分支。"""
    import subprocess
    d = _tmp()
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "tools", "fea_screen.py")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for case, extra in (("bracket", ["--length", "200", "--root-h", "30",
                                     "--tip-h", "10", "--width", "20"]),
                        ("stepped", ["--segments", "20x60,12x40,16x100", "--nu", "0"])):
        out_png = os.path.join(d, "%s.png" % case)
        res = subprocess.run([sys.executable, script, "--case", case, "--force", "100",
                              "--png", out_png] + extra,
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", env=env, timeout=600)
        assert res.returncode in (0, 1), res.stdout + res.stderr
        assert os.path.isfile(out_png), "%s 分支没出图：%s" % (case, res.stdout[-300:])
        assert open(out_png, "rb").read(8) == b"\x89PNG\r\n\x1a\n"


@need
def test_deformed_png_rejects_bad_result() -> None:
    d = _tmp()
    with pytest.raises(M.FeaError):
        V.deformed_from_result({"displacements": {1: (0, 0, 0)}}, os.path.join(d, "a.png"))
    mesh = M.box_mesh(10, 10, 10, mesh_size=10)
    with pytest.raises(M.FeaError):
        V.deformed_png(mesh, {}, os.path.join(d, "b.png"))
    with pytest.raises(M.FeaError):
        V.deformed_png(mesh, {1: (0.0, 0.0, 0.0)}, os.path.join(d, "no_dir", "c.png"))
