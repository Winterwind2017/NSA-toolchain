"""FEA 结果可视化：变形云图（边界曲面 + |u| 着色）。

只画**外表面**：四面体网格的边界三角形（被一个单元独占的面）。这样
* 不需要把 1000+ 个四面体塞进 GPU；
* 人看到的正是"件被拉/弯成什么样"。

判据同 brep.render：PNG 魔数、非空白、且**颜色真有分布**（最大/最小像素不同），
否则可能画出单色块。

变形放大系数：默认把最大位移放大到包围盒对角线的 15%，保证肉眼可见；
显式给 `scale` 就用给定值（并在结果里回传，便于复现）。
"""

from __future__ import annotations

import math
import os
from collections import Counter
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

from .mesh import FeaError, TetMesh

DEFAULT_COLOR = "#c9ced6"
MIN_PIXEL_STD = 2.0


def _pv():
    try:
        import pyvista
    except Exception as exc:                                  # noqa: BLE001
        raise FeaError("可视化需要 pyvista：%s" % exc) from exc
    pyvista.OFF_SCREEN = True
    return pyvista


def boundary_triangles(mesh: TetMesh) -> list:
    """只被一个四面体拥有的面 = 外表面。"""
    cnt: Counter = Counter()
    for a, b, c, d in mesh.tets:
        for tri in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
            cnt[tuple(sorted(tri))] += 1
    return [tri for tri, k in cnt.items() if k == 1]


def auto_scale(mesh: TetMesh, disp: np.ndarray, target: float = 0.15) -> float:
    """把最大位移放大到 包围盒对角线×target。"""
    b = mesh.bbox()
    diag = math.sqrt((b["xmax"] - b["xmin"]) ** 2 + (b["ymax"] - b["ymin"]) ** 2
                     + (b["zmax"] - b["zmin"]) ** 2)
    peak = float(np.abs(disp).max()) if disp.size else 0.0
    if peak <= 0 or diag <= 0:
        return 1.0
    return max(target * diag / peak, 1e-9)


def deformed_png(mesh: TetMesh, displacements: Dict[int, Tuple[float, float, float]],
                 path: str, *, scale: Optional[float] = None,
                 target_ratio: float = 0.15,
                 size: Tuple[int, int] = (1000, 700), cmap: str = "turbo",
                 camera: str = "iso", show_edges: bool = False) -> Dict[str, object]:
    """变形云图：位移场 → 曲面外表面 + 按 |u| 着色。

    displacements: {节点号: (ux,uy,uz)}，只包含被打印的节点（MEASURE 集合）。
    缺失节点按 0 位移处理（并在结果里报 missing 数量）。
    """
    pv = _pv()
    if not displacements:
        raise FeaError("没有位移数据，无法出图")
    tris = boundary_triangles(mesh)
    if not tris:
        raise FeaError("网格没有边界三角形（不是闭合体？）")

    keys = sorted(mesh.nodes)
    idx = {k: i for i, k in enumerate(keys)}
    P = np.array([mesh.nodes[k] for k in keys], dtype=float)
    U = np.zeros_like(P)
    missing = 0
    for n, v in displacements.items():
        if n in idx:
            U[idx[n]] = (float(v[0]), float(v[1]), float(v[2]))
        else:
            missing += 1
    mag = np.linalg.norm(U, axis=1)

    s = float(scale) if scale is not None else auto_scale(mesh, U, target_ratio)
    Pd = P + U * s

    faces = np.hstack([np.full((len(tris), 1), 3),
                       np.array([[idx[i] for i in t] for t in tris], dtype=np.int64)]
                      ).astype(np.int64).ravel()
    surf = pv.PolyData(Pd, faces)
    surf["u_mag"] = mag

    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        raise FeaError("父目录不存在：%s" % parent)

    plotter = pv.Plotter(off_screen=True, window_size=size)
    try:
        plotter.add_mesh(surf, scalars="u_mag", cmap=cmap, show_edges=show_edges,
                         edge_color="#30343c", scalar_bar_args={"title": "|u| (mm)"})
        plotter.add_text("magnified x%.0f" % s, font_size=9, color="black")
        plotter.camera_position = camera
        plotter.reset_camera()
        img = np.asarray(plotter.screenshot(return_img=True))
    finally:
        plotter.close()

    import imageio.v3 as iio
    iio.imwrite(path, img)
    if open(path, "rb").read(8) != b"\x89PNG\r\n\x1a\n":
        raise FeaError("PNG 魔数不对：%s" % path)
    stats = {"path": os.path.abspath(path), "bytes": os.path.getsize(path),
             "size": [int(img.shape[1]), int(img.shape[0])],
             "pixel_std": float(img.std()),
             "triangles": len(tris), "scale": s, "missing_nodes": missing,
             "max_disp": float(mag.max()) if mag.size else 0.0,
             "min_disp": float(mag.min()) if mag.size else 0.0,
             "color_spread": int(img.max()) - int(img.min())}
    if float(stats["pixel_std"]) < MIN_PIXEL_STD:
        raise FeaError("云图接近空白（pixel_std=%.3f）" % float(stats["pixel_std"]))
    if float(stats["max_disp"]) <= 0:
        raise FeaError("位移全为 0，画出来没有意义")
    return stats


def deformed_from_result(result: Dict[str, object], path: str, *,
                         mesh: Optional[TetMesh] = None,
                         **kwargs) -> Dict[str, object]:
    """直接从 brep_bridge/cases 的结果字典出图。

    结果里若带 `mesh_obj`（TetMesh）就用它；否则必须显式传 mesh。
    """
    m = mesh or result.get("mesh_obj")            # type: ignore[assignment]
    if m is None:
        raise FeaError("结果里没有 mesh_obj，请显式传 mesh=")
    disp = result.get("displacements") or {}
    if not isinstance(disp, dict) or not disp:
        raise FeaError("结果里没有 displacements")
    return deformed_png(m, disp, path, **kwargs)   # type: ignore[arg-type]
