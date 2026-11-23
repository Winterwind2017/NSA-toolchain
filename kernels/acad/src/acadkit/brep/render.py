"""零件出图：等轴测/三视图 PNG + 线框 SVG（离线、不依赖 CAD 软件）。

为什么放这里：`brep` 造完件只能出 STEP，人看不到形状，agent 的结论就少一半说服力。
cadquery 自带三角化，pyvista 负责离屏渲染（Windows 上走 WGL，已实测可用）。

判据不只看"文件生成了"：
* PNG 魔数 + 尺寸；
* **非空白**：像素标准差 > 阈值（全白/全黑会接近 0）；
* **视角真有差别**：两个视角的 PNG 字节不同（否则说明相机没生效）。

渲染坐标说明：cadquery 的 Z 向上，pyvista 默认 Y 向上，这里统一用
`camera_position='xz'` 类字符串由 pyvista 处理，避免手工换轴出错。
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .parts import BrepError, Part

DEFAULT_COLOR = "#c9ced6"
DEFAULT_EDGE = "#4a5060"
MIN_PIXEL_STD = 2.0        # 低于这个标准差就当"空白图"


def _pv():
    try:
        import pyvista
    except Exception as exc:                                  # noqa: BLE001
        raise BrepError("渲染需要 pyvista：%s" % exc) from exc
    pyvista.OFF_SCREEN = True
    return pyvista


def _xyz(v) -> Tuple[float, float, float]:
    for attr in ("toTuple",):
        if hasattr(v, attr):
            return tuple(float(x) for x in v.toTuple())      # type: ignore[no-any-return]
    if hasattr(v, "x"):
        return (float(v.x), float(v.y), float(v.z))
    return tuple(float(x) for x in v)                        # type: ignore[return-value]


def polydata(part: Part, tolerance: float = 0.2):
    """零件 → pyvista.PolyData（三角化表面）。"""
    pv = _pv()
    if not hasattr(part, "obj"):
        raise BrepError("part 需要是 acadkit.brep.parts.Part")
    if not (tolerance > 0):
        raise BrepError("tolerance 必须为正")
    verts, tris = part.obj.val().tessellate(float(tolerance))
    if not len(tris):
        raise BrepError("三角化失败（没有三角形）")
    P = np.array([_xyz(v) for v in verts], dtype=float)
    T = np.asarray(tris, dtype=np.int64)
    faces = np.hstack([np.full((len(T), 1), 3), T]).astype(np.int64).ravel()
    return pv.PolyData(P, faces)


# pyvista 只接受 xy/xz/yz/yx/zx/zy/iso 这七个相机名
VIEWS = {
    "iso": "iso",      # 等轴测
    "front": "xz",     # 前视（沿 -Y 看，Z 向上）
    "top": "xy",       # 俯视（沿 -Z 看）
    "right": "yz",     # 右视（沿 -X 看）
}


def _render(mesh, view: str, *, size: Tuple[int, int], color: str,
            edge_color: str, show_edges: bool, title: str = "") -> np.ndarray:
    pv = _pv()
    plotter = pv.Plotter(off_screen=True, window_size=size)
    try:
        plotter.add_mesh(mesh, color=color, show_edges=show_edges,
                         edge_color=edge_color, smooth_shading=False)
        if title:
            plotter.add_text(title, font_size=9, color="black")
        plotter.camera_position = VIEWS.get(view, VIEWS["iso"])
        plotter.reset_camera()
        img = plotter.screenshot(return_img=True)
    finally:
        plotter.close()
    arr = np.asarray(img)
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise BrepError("截图数组形状异常：%r" % (arr.shape,))
    return arr


def _save_png(arr: np.ndarray, path: str) -> Dict[str, object]:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        raise BrepError("父目录不存在：%s" % parent)
    import imageio.v3 as iio
    iio.imwrite(path, arr)
    if not os.path.isfile(path):
        raise BrepError("PNG 没写出来：%s" % path)
    head = open(path, "rb").read(8)
    if head != b"\x89PNG\r\n\x1a\n":
        raise BrepError("PNG 魔数不对：%s" % path)
    return {"path": os.path.abspath(path), "bytes": os.path.getsize(path),
            "size": [int(arr.shape[1]), int(arr.shape[0])],
            "pixel_std": float(arr.std())}


def _assert_not_blank(stats: Dict[str, object], view: str) -> None:
    if float(stats["pixel_std"]) < MIN_PIXEL_STD:
        raise BrepError("渲染出来接近空白（pixel_std=%.3f < %.1f，view=%s）"
                        % (float(stats["pixel_std"]), MIN_PIXEL_STD, view))


def iso_png(part: Part, path: str, *, size: Tuple[int, int] = (900, 650),
            color: str = DEFAULT_COLOR, edge_color: str = DEFAULT_EDGE,
            show_edges: bool = True) -> Dict[str, object]:
    """单张等轴测 PNG。返回 {path, bytes, size, pixel_std}。"""
    mesh = polydata(part)
    arr = _render(mesh, "iso", size=size, color=color, edge_color=edge_color,
                  show_edges=show_edges, title=part.name)
    stats = _save_png(arr, path)
    _assert_not_blank(stats, "iso")
    return stats


def three_view_png(part: Part, path: str, *, size: Tuple[int, int] = (1200, 420),
                   views: Sequence[str] = ("front", "top", "right"),
                   color: str = DEFAULT_COLOR, edge_color: str = DEFAULT_EDGE,
                   show_edges: bool = True) -> Dict[str, object]:
    """三视图拼一张 PNG（横向拼接，标签为视角名）。

    拼接用 numpy（不引入 PIL 依赖差异）；每张先保证非空白。
    """
    if not views:
        raise BrepError("views 不能为空")
    per = (max(size[0] // len(views), 200), size[1])
    mesh = polydata(part)
    panels: List[np.ndarray] = []
    for v in views:
        arr = _render(mesh, v, size=per, color=color, edge_color=edge_color,
                      show_edges=show_edges, title="%s (%s)" % (part.name, v))
        panel_stats = {"pixel_std": float(arr.std())}
        _assert_not_blank(panel_stats, v)
        panels.append(arr)
    h = min(p.shape[0] for p in panels)
    combined = np.hstack([p[:h, :, :3] for p in panels])
    stats = _save_png(combined, path)
    _assert_not_blank(stats, "three_view")
    stats["views"] = list(views)
    return stats


def svg_views(part: Part, path: str, *, width: float = 200, height: float = 150,
              margin: float = 6) -> Dict[str, object]:
    """线框 SVG（带隐藏线，cadquery 导出器）。适合进文档/网页，体积小。"""
    if not hasattr(part, "obj"):
        raise BrepError("part 需要是 acadkit.brep.parts.Part")
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        raise BrepError("父目录不存在：%s" % parent)
    try:
        import cadquery as cq
    except Exception as exc:                                  # noqa: BLE001
        raise BrepError("SVG 导出需要 cadquery：%s" % exc) from exc
    cq.exporters.export(part.obj, path, opt={
        "width": float(width), "height": float(height), "marginLeft": float(margin),
        "marginTop": float(margin), "showAxes": False, "projectionDir": (1, 1, 0.6),
        "strokeWidth": 0.3, "strokeColor": (40, 40, 40),
        "hiddenColor": (120, 120, 120), "showHidden": True})
    if not os.path.isfile(path):
        raise BrepError("SVG 没写出来：%s" % path)
    text = open(path, encoding="utf-8", errors="replace").read()
    paths = text.count("<path")
    if paths < 1:
        raise BrepError("SVG 里没有路径（paths=0）")
    return {"path": os.path.abspath(path), "bytes": os.path.getsize(path),
            "paths": paths, "has_hidden": "stroke-dasharray" in text}
