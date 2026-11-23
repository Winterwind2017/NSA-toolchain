"""离线正式图纸：三视图线框 + 图框 + 标题栏 → 矢量 PDF。

为什么要有这条路：真机 AutoCAD/SolidWorks 出图很强，但**换机器 / CI / 客户现场没有 CAD**
时就断了。这里用 cadquery 的 HLR（隐藏线消除）投影出线框，matplotlib 画成真正的矢量 PDF。

隐藏线的判定方式：**导出两次做差集**。
    hidden = paths(showHidden=True) − paths(showHidden=False)
不依赖 SVG 内部的分组/样式细节（cadquery 把隐藏线放在一个带 dasharray 的组里，
但那是实现细节，版本一变就失效）。

判据（写进 verify_pdf）：PDF 头、单页、A3 幅面（420×297 mm）、标题栏文字可提取、
线框段数 > 0。中文能否被 pypdf 提取取决于字体嵌入，提不出来就如实标
`text_extractable=False`，不假装通过。
"""

from __future__ import annotations

import math
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .parts import BrepError, Part

# 视角 → 投影方向（cadquery 的 projectionDir）
VIEW_DIRS: Dict[str, Tuple[float, float, float]] = {
    "front": (0.0, -1.0, 0.0),
    "top": (0.0, 0.0, 1.0),
    "right": (1.0, 0.0, 0.0),
    "iso": (1.0, 1.0, 0.6),
}
VIEW_LABEL = {"front": "前视", "top": "俯视", "right": "右视", "iso": "等轴测"}

SHEETS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0)}
STD_SCALES = (10.0, 5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01)

Polyline = List[Tuple[float, float]]


def _svg_text(part: Part, direction: Sequence[float], *, width: float,
              height: float, show_hidden: bool) -> str:
    from cadquery.occ_impl.exporters.svg import getSVG
    opts = {"width": float(width), "height": float(height),
            "marginLeft": 0, "marginTop": 0, "showAxes": False,
            "projectionDir": tuple(float(x) for x in direction),
            "strokeWidth": 0.3, "showHidden": bool(show_hidden),
            "hiddenColor": (120, 120, 120), "strokeColor": (0, 0, 0)}
    shape = part.obj.val() if hasattr(part.obj, "val") else part.obj
    try:
        return getSVG(shape, opts)
    except Exception as exc:                          # noqa: BLE001
        raise BrepError("HLR 投影失败：%s" % exc) from exc


def _paths(svg: str) -> List[str]:
    return [m.group(1) for m in re.finditer(r'<path[^>]*\sd="([^"]+)"', svg)]


def _polyline(d: str) -> Optional[Polyline]:
    """把 "M x,y L x,y ..." 解析成点列；曲线指令直接放弃（本导出器只出折线）。"""
    if not d or ("C" in d.upper().replace("M", "").replace("L", "")):
        return None
    nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", d)
    vals = [float(x) for x in nums]
    if len(vals) < 4 or len(vals) % 2:
        return None
    pts = [(vals[i], vals[i + 1]) for i in range(0, len(vals), 2)]
    return pts


def project(part: Part, view: str = "front", *, size: Tuple[float, float] = (200.0, 150.0)
            ) -> Dict[str, object]:
    """单视角投影：返回 {"visible": [...], "hidden": [...], "bbox": (...)}。"""
    if view not in VIEW_DIRS:
        raise BrepError("未知视角 %r（可用：%s）" % (view, ", ".join(VIEW_DIRS)))
    if not hasattr(part, "obj"):
        raise BrepError("part 需要是 acadkit.brep.parts.Part")
    w, h = float(size[0]), float(size[1])

    with_hidden = _paths(_svg_text(part, VIEW_DIRS[view], width=w, height=h,
                                   show_hidden=True))
    visible_only = _paths(_svg_text(part, VIEW_DIRS[view], width=w, height=h,
                                    show_hidden=False))

    # 差集：只在 showHidden=True 里出现的，就是隐藏线（按出现次数配平）
    from collections import Counter
    cnt_all = Counter(with_hidden)
    cnt_vis = Counter(visible_only)
    hidden_d: List[str] = []
    for d, n in cnt_all.items():
        extra = n - cnt_vis.get(d, 0)
        hidden_d.extend([d] * max(extra, 0))
    visible_d = list(visible_only)

    vis = [p for p in (_polyline(d) for d in visible_d) if p]
    hid = [p for p in (_polyline(d) for d in hidden_d) if p]
    if not vis:
        raise BrepError("没有可见线（零件为空或投影方向不对）")

    xs = [x for pl in vis + hid for x, _y in pl]
    ys = [y for pl in vis + hid for _x, y in pl]
    return {"visible": vis, "hidden": hid,
            "bbox": (min(xs), min(ys), max(xs), max(ys)),
            "counts": {"visible": len(vis), "hidden": len(hid)}}


def _pick_scale(views: Dict[str, Dict[str, object]], cells: Dict[str, Tuple[float, float]],
                max_scale: float = 1.0) -> float:
    """所有视图共用一个比例（工程图规矩），取能塞进各自格子的最大值，再落到标准序列。"""
    fit = max_scale
    for name, pr in views.items():
        cw, ch = cells[name]
        x0, y0, x1, y1 = pr["bbox"]                     # type: ignore[misc]
        bw, bh = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
        fit = min(fit, cw / bw, ch / bh)
    for s in STD_SCALES:
        if s <= fit + 1e-12:
            return s
    return STD_SCALES[-1]


def _scale_label(scale: float) -> str:
    if scale >= 1:
        return "%g:1" % round(scale, 3)
    return "1:%g" % round(1.0 / scale, 3)


def _setup_font() -> str:
    """尽量用中文字体；没有就退回英文标签（并如实上报）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as rc
    names = {f.name for f in fm.fontManager.ttflist}
    for cand in ("Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC"):
        if cand in names:
            rc.rcParams["font.sans-serif"] = [cand, "DejaVu Sans"]
            rc.rcParams["axes.unicode_minus"] = False
            rc.rcParams["pdf.fonttype"] = 42
            rc.rcParams["pdf.compression"] = 0
            return cand
    rc.rcParams["pdf.fonttype"] = 42
    rc.rcParams["pdf.compression"] = 0
    return ""


def sheet_pdf(part: Part, path: str, *, sheet: str = "A3",
              views: Sequence[str] = ("front", "top", "right"),
              title_block: Optional[Dict[str, str]] = None,
              margin: float = 10.0, max_scale: float = 1.0) -> Dict[str, object]:
    """出图：三视图线框 + 图框 + 标题栏，写矢量 PDF。"""
    if sheet.upper() not in SHEETS:
        raise BrepError("未知图幅 %r（可用：%s）" % (sheet, ", ".join(SHEETS)))
    if not views:
        raise BrepError("views 不能为空")
    for v in views:
        if v not in VIEW_DIRS:
            raise BrepError("未知视角 %r" % (v,))
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        raise BrepError("父目录不存在：%s" % parent)

    pw, ph = SHEETS[sheet.upper()]
    font = _setup_font()
    chinese = bool(font)

    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    # ── 布局：主视左上，俯视在正下方，右视在主视右侧（GB 第一角习惯），整组居中 ──
    inner_w, inner_h = pw - 2 * margin, ph - 2 * margin
    tb_w, tb_h = min(190.0, inner_w * 0.55), min(45.0, inner_h * 0.22)
    area_x0, area_y0 = margin + 8.0, margin + tb_h + 8.0
    area_x1, area_y1 = pw - margin - 8.0, ph - margin - 8.0
    avail_w, avail_h = area_x1 - area_x0, area_y1 - area_y0
    gap = 12.0

    proj: Dict[str, Dict[str, object]] = {}
    for name in views:
        proj[name] = project(part, name, size=(220.0, 170.0))

    def _dim(name: str) -> Tuple[float, float]:
        x0, y0, x1, y1 = proj[name]["bbox"]            # type: ignore[misc]
        return (max(x1 - x0, 1e-9), max(y1 - y0, 1e-9))

    def _has(name: str) -> bool:
        return name in proj

    bw_front, bh_front = _dim("front") if _has("front") else _dim(views[0])
    bw_top, bh_top = _dim("top") if _has("top") else (0.0, 0.0)
    bw_right, bh_right = _dim("right") if _has("right") else (0.0, 0.0)

    col_left_w = max(bw_front, bw_top)
    group_w = col_left_w + (gap + bw_right if _has("right") else 0.0)
    rows = []
    if _has("front") or not _has("top"):
        rows.append(bh_front)
    if _has("top"):
        rows.append(bh_top)
    group_h = sum(rows) + gap * max(len(rows) - 1, 0)

    fit = min(avail_w / group_w, avail_h / group_h, float(max_scale))
    scale = STD_SCALES[-1]
    for cand in STD_SCALES:
        if cand <= fit + 1e-12:
            scale = cand
            break
    label = _scale_label(scale)

    gx = area_x0 + (avail_w - group_w * scale) / 2.0
    gy = area_y1 - (avail_h - group_h * scale) / 2.0
    layout: Dict[str, Tuple[float, float, float, float]] = {}
    if _has("front"):
        fw, fh = bw_front * scale, bh_front * scale
        layout["front"] = (gx + (col_left_w * scale - fw) / 2.0, gy - fh, fw, fh)
    if _has("top"):
        tw, th = bw_top * scale, bh_top * scale
        y_top = gy - bh_front * scale - gap
        layout["top"] = (gx + (col_left_w * scale - tw) / 2.0, y_top - th, tw, th)
    if _has("right"):
        rw, rh = bw_right * scale, bh_right * scale
        layout["right"] = (gx + col_left_w * scale + gap, gy - rh, rw, rh)
    for name in views:                                   # 兜底：没安排的视角并排放
        if name not in layout:
            w_, h_ = _dim(name)
            layout[name] = (gx, gy - h_ * scale, w_ * scale, h_ * scale)

    fig = plt.figure(figsize=(pw / 25.4, ph / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, pw)
    ax.set_ylim(0, ph)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.add_patch(Rectangle((margin, margin), inner_w, inner_h, fill=False, lw=0.9))
    ax.add_patch(Rectangle((margin - 4, margin - 4), inner_w + 8, inner_h + 8,
                           fill=False, lw=0.4))

    seg_vis = seg_hid = 0
    for name in views:
        bx, by, bw, bh = layout[name]
        pr = proj[name]
        x0, y0, x1, y1 = pr["bbox"]                     # type: ignore[misc]
        ox = bx + (bw - (x1 - x0) * scale) / 2.0 - x0 * scale
        oy = by + (bh - (y1 - y0) * scale) / 2.0 - y0 * scale

        def _draw(lines, hidden: bool) -> int:
            n = 0
            for pl in lines:
                xs = [ox + x * scale for x, _yy in pl]
                ys = [oy + y * scale for _xx, y in pl]
                ax.plot(xs, ys, color=("#666666" if hidden else "#111111"),
                        lw=(0.22 if hidden else 0.35),
                        ls=((0, (4, 2)) if hidden else "-"),
                        solid_capstyle="round", zorder=2 if hidden else 3)
                n += 1
            return n

        seg_vis += _draw(pr["visible"], False)            # type: ignore[arg-type]
        seg_hid += _draw(pr["hidden"], True)             # type: ignore[arg-type]
        ax.text(bx + bw / 2.0, by - 3.5,
                (VIEW_LABEL[name] if chinese else name),
                fontsize=6.5, ha="center", va="top", color="#111111")

    # 标题栏
    tb = dict(title_block or {})
    fields = [("图名", tb.get("title", "")), ("图号", tb.get("number", "")),
              ("材料", tb.get("material", "")), ("比例", tb.get("scale") or label),
              ("日期", tb.get("date", "")), ("单位", tb.get("company", "nsa-toolchain"))]
    tx, ty = pw - margin - tb_w, margin
    ax.add_patch(Rectangle((tx, ty), tb_w, tb_h, fill=False, lw=0.8))
    for i in range(1, len(fields)):
        y = ty + tb_h - i * (tb_h / len(fields))
        ax.plot([tx, tx + tb_w], [y, y], color="#000000", lw=0.3)
    ax.plot([tx + tb_w * 0.32, tx + tb_w * 0.32], [ty, ty + tb_h],
            color="#000000", lw=0.3)
    for i, (k, v) in enumerate(fields):
        y = ty + tb_h - (i + 0.5) * (tb_h / len(fields))
        ax.text(tx + 2.0, y, (k if chinese else k), fontsize=6,
                ha="left", va="center")
        ax.text(tx + tb_w * 0.32 + 2.0, y, str(v) if v else "", fontsize=6,
                ha="left", va="center")
    ax.text(tx + 2.0, ty + tb_h + 1.5, "%s %s" % (sheet.upper(), label),
            fontsize=5.5, ha="left", va="bottom", color="#444444")

    fig.savefig(path, format="pdf")
    plt.close(fig)

    if not os.path.isfile(path):
        raise BrepError("PDF 没写出来：%s" % path)
    stats = {"path": os.path.abspath(path), "bytes": os.path.getsize(path),
             "sheet": sheet.upper(), "page_mm": [pw, ph], "scale": scale,
             "scale_label": label, "views": list(views),
             "segments_visible": seg_vis, "segments_hidden": seg_hid,
             "font": font, "chinese_labels": chinese,
             "fields": {k: str(v) for k, v in fields}}
    stats.update(verify_pdf(path, expect_text=[v for _k, v in fields if v],
                            page_mm=(pw, ph)))
    return stats


def verify_pdf(path: str, *, expect_text: Sequence[str] = (),
               page_mm: Optional[Tuple[float, float]] = None) -> Dict[str, object]:
    """独立复核：页数 / 幅面 / 文字 / 向量算子。"""
    if not os.path.isfile(path):
        raise BrepError("PDF 不存在：%s" % path)
    head = open(path, "rb").read(5)
    if head != b"%PDF-":
        raise BrepError("PDF 头不对：%r" % head)
    out: Dict[str, object] = {"header_ok": True}
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        out["pages"] = len(reader.pages)
        box = reader.pages[0].mediabox
        w_pt, h_pt = float(box.width), float(box.height)
        out["page_pt"] = [round(w_pt, 2), round(h_pt, 2)]
        out["page_mm"] = [round(w_pt / 72.0 * 25.4, 2), round(h_pt / 72.0 * 25.4, 2)]
        if page_mm:
            ok_w = abs(out["page_mm"][0] - page_mm[0]) < 1.5      # type: ignore[index]
            ok_h = abs(out["page_mm"][1] - page_mm[1]) < 1.5      # type: ignore[index]
            out["page_size_ok"] = bool(ok_w and ok_h)
        text = ""
        try:
            text = reader.pages[0].extract_text() or ""
        except Exception:                            # noqa: BLE001
            text = ""
        out["text_chars"] = len(text)
        out["text_extractable"] = bool(text.strip())
        missing = [t for t in expect_text if str(t) and str(t) not in text]
        out["missing_text"] = missing
        out["text_ok"] = not missing
    except ImportError:
        out["pages"] = None
        out["note"] = "未安装 pypdf，跳过页数/幅面/文字复核"
    raw = open(path, "rb").read()
    out["has_vector_ops"] = (b" m\n" in raw) or (b" l\n" in raw) or (b" re\n" in raw)
    return out
