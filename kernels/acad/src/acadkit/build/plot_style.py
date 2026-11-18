"""打印样式 / 线宽出图（`plot.style`）：把"线宽有没有真的出到纸上"做成可判的事实。

本机实测（2026-11-18，AutoCAD 2025 / R25.0）：

* `AcadLayout` **有** `StyleSheet`（CTB/STB 表名）与 `GetPlotStyleTableNames()`；
  `PlotWithPlotStyles`、`PlotWithLineweights`、`ScaleLineweights` 都是可读写布尔；
* `doc.Plot` 只有 PlotToFile 一类方法，**没有**直接指定样式表的入口，
  所以样式表必须写在 layout 上；
* `PSTYLEMODE=1`（命名 STB）——切模式要重开图纸，本能力**不动它**，
  只在自己可写的范围内作业；
* `Layer.Lineweight` 可写（-3 = 默认，100 = 1.00mm，13 = 0.13mm）。

因此本能力做两件可证的事，而不是"设了就算成功"：

1. **对象线宽真的影响出图**：同一条几何，`PlotWithLineweights=True` 出的 PDF
   与 `False` 出的 PDF，墨量必须有显著差异（判据用像素级墨量比）；
2. **样式表真的挂上去了**：`StyleSheet` 读回 == 请求的表名。

墨量由判据自己从两个 PDF 里数（不采信 builder 的说法）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from ..core import com, plot as plotmod
from .helpers import dbl, pt


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def _ensure_layer(doc: Any, name: str, color: int, lineweight: int) -> Dict[str, Any]:
    """建（或复用）一个带指定颜色/线宽的图层，返回读回值。"""
    layers = com.retry(lambda: doc.Layers, label="Layers")
    try:
        lay = layers.Item(name)
    except Exception:                               # noqa: BLE001
        lay = com.retry(lambda: layers.Add(name), label="Layers.Add(%s)" % name)
    com.retry(lambda: setattr(lay, "color", int(color)), label="Layer.color")
    com.retry(lambda: setattr(lay, "Lineweight", int(lineweight)),
              label="Layer.Lineweight")
    return {"name": str(lay.Name), "color": int(lay.color),
            "lineweight": int(lay.Lineweight),
            "plot_style": str(getattr(lay, "PlotStyleName", ""))}


def _pick_style_table(layout: Any) -> Tuple[str, List[str]]:
    """挑一个单色打印样式表；拿不到就返回空串（判据会因此失败，不假装成功）。"""
    names: List[str] = []
    try:
        names = [str(x) for x in (layout.GetPlotStyleTableNames() or [])]
    except Exception:                               # noqa: BLE001
        names = []
    for cand in names:
        low = cand.lower()
        if "mono" in low and (low.endswith(".ctb") or low.endswith(".stb")):
            return cand, names
    for cand in names:
        low = cand.lower()
        if low.endswith(".ctb") or low.endswith(".stb"):
            return cand, names
    return "", names


def build_plot_style(doc: Any, ctx: Dict[str, Any]) -> None:
    """两个带线宽的图层 + 三条线，出三张 PDF：样式表 / 有线宽 / 无线宽。"""
    workdir = ctx["workdir"]
    thick_lw = int(_p(ctx, "thick_lineweight", 100))     # 1.00 mm
    thin_lw = int(_p(ctx, "thin_lineweight", 13))        # 0.13 mm
    table = str(_p(ctx, "style_table", "monochrome.ctb"))

    lay_thick = _ensure_layer(doc, "AK_THICK", 1, thick_lw)   # 红
    lay_thin = _ensure_layer(doc, "AK_THIN", 5, thin_lw)      # 蓝
    doc.SetVariable("LWDISPLAY", 1)

    ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
    for layer in ("AK_THICK", "AK_THIN"):
        doc.ActiveLayer = com.retry(lambda n=layer: doc.Layers.Item(n),
                                    label="ActiveLayer")
        for y in (0.0, 40.0, 80.0):
            pl = com.retry(lambda yy=y: ms.AddLightWeightPolyline(
                dbl([10, yy, 120, yy, 120, yy + 25, 10, yy + 25])),
                label="AddLightWeightPolyline")
            pl.Closed = True
    doc.ActiveLayer = com.retry(lambda: doc.Layers.Item("0"), label="ActiveLayer(0)")

    layout = com.retry(lambda: doc.ActiveLayout, label="ActiveLayout")
    tables = []
    try:
        tables = [str(x) for x in (layout.GetPlotStyleTableNames() or [])]
    except Exception:                               # noqa: BLE001
        tables = []
    chosen = table if table in tables else _pick_style_table(layout)[0]
    applied = {"requested": chosen, "readback": None, "error": None}
    if chosen:
        try:
            layout.StyleSheet = chosen
            applied["readback"] = str(layout.StyleSheet)
        except Exception as exc:                    # noqa: BLE001
            applied["error"] = "%s: %s" % (type(exc).__name__, exc)

    paths = {
        "style": os.path.join(workdir, "plot_style_stylesheet.pdf"),
        "lineweight_on": os.path.join(workdir, "plot_style_lw_on.pdf"),
        "lineweight_off": os.path.join(workdir, "plot_style_lw_off.pdf"),
    }

    # A) 挂样式表出图（PlotWithPlotStyles=True）
    infoA = plotmod.plot_model_to_pdf(doc, paths["style"], with_plot_styles=True)

    # B) 用对象线宽出图（关掉样式表，否则样式表会盖掉线宽）
    layout.PlotWithLineweights = True
    infoB = plotmod.plot_model_to_pdf(doc, paths["lineweight_on"], with_plot_styles=False)

    # C) 关掉线宽出图（同样的几何，线宽不起作用）
    layout.PlotWithLineweights = False
    infoC = plotmod.plot_model_to_pdf(doc, paths["lineweight_off"], with_plot_styles=False)
    layout.PlotWithLineweights = True

    ctx.setdefault("artifacts", {})["plot_style"] = {
        "layers": {"thick": lay_thick, "thin": lay_thin},
        "lineweights": {"thick": thick_lw, "thin": thin_lw},
        "style_table": applied,
        "style_tables_seen": tables[:20],
        "paths": paths,
        "plot": {"style": infoA, "lineweight_on": infoB, "lineweight_off": infoC},
        "readback": {
            "style_sheet": (applied["readback"] or ""),
            "plot_with_lineweights": bool(layout.PlotWithLineweights),
            "plot_with_plotstyles": bool(layout.PlotWithPlotStyles),
        },
    }
