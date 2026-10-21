"""导出类 builder：DWG（存盘）/ DXF / PDF。"""

from __future__ import annotations

import os
from typing import Any, Dict

from ..core import com, plot as plotmod
from .helpers import basic_drawing, dbl, pt


def build_dwg(doc: Any, ctx: Dict[str, Any]) -> None:
    basic_drawing(doc)


def build_dxf(doc: Any, ctx: Dict[str, Any]) -> None:
    basic_drawing(doc)
    path = os.path.join(ctx["workdir"], "export_dxf.dxf")
    info = plotmod.save_as(doc, path, fmt=65)
    ctx["artifacts"]["dxf_path"] = path
    ctx["artifacts"]["dxf_save"] = info
    if not info.get("ok"):
        ctx["notes"].append("DXF 落盘失败：%r" % (info,))


def build_pdf(doc: Any, ctx: Dict[str, Any]) -> None:
    ms = basic_drawing(doc)
    pl = com.retry(lambda: ms.AddLightWeightPolyline(
        dbl([0, 0, 40, 0, 40, 30, 0, 30])), label="AddLightWeightPolyline")
    pl.Closed = True
    com.retry(lambda: ms.AddText("ACADKIT JUDGE", pt(0, 40, 0), 5.0),
              label="AddText")
    path = os.path.join(ctx["workdir"], "export_pdf.pdf")
    info = plotmod.plot_model_to_pdf(doc, path)
    ctx["artifacts"]["pdf_path"] = path
    ctx["artifacts"]["plot"] = info
