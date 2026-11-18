"""导出类 builder：DWG（存盘）/ DXF / PDF。"""

from __future__ import annotations

import os
import time
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


def _add_paper_circle(doc: Any, radius: float, attempts: int = 6) -> None:
    """在活动布局的图纸空间画圆；切换布局后 COM 句柄偶发失效，重试。

    实测（2026-11-18，alpha gate W4）：先跑过 `layout.multipage` 再切两次布局，
    `doc.PaperSpace.AddCircle` 偶发抛 `AttributeError: <unknown>.AddCircle`
    （拿到的是旧句柄）。这里每次重试都重新取 `PaperSpace`，并把 `ActiveLayout`
    触碰一次促使 COM 重绑；6 次仍失败才抛。
    """
    last: Any = None
    for i in range(attempts):
        try:
            ps = doc.PaperSpace
            ps.AddCircle(pt(100, 100, 0), radius)
            return
        except Exception as exc:                    # noqa: BLE001
            last = exc
            time.sleep(0.25 * (i + 1))
            try:
                doc.ActiveLayout = doc.ActiveLayout  # 触碰，促使 COM 重绑
            except Exception:                        # noqa: BLE001
                pass
    raise RuntimeError("PaperSpace.AddCircle 失败：%s: %s"
                       % (type(last).__name__, last))


def build_pdf_multipage(doc: Any, ctx: Dict[str, Any]) -> None:
    """多布局出图：每个布局单独出 PDF，再用 pypdf 合并成多页。

    本机实测（2026-10-21）：ActiveX `Plot.SetLayoutsToPlot` + `PlotToFile`
    产不出多页文件（带 `StartBatchMode` 直接失败），`-PUBLISH` 会阻塞。
    所以"正确路径"是**逐布局出图 + 合并**，合并用 pypdf（`acadkit[pdf]`）。
    """
    try:
        from pypdf import PdfWriter  # noqa: F401
    except Exception as exc:                        # noqa: BLE001
        ctx["notes"].append("缺少 pypdf（pip install 'acadkit[pdf]'）：%s" % exc)
        return

    pages = []
    layouts = com.retry(lambda: doc.Layouts, label="Layouts")
    for name, radius in (("S1", 30.0), ("S2", 20.0)):
        try:
            layouts.Item(name)
        except Exception:                           # noqa: BLE001
            com.retry(lambda n=name: layouts.Add(n), label="Layouts.Add")
        doc.ActiveLayout = com.retry(lambda n=name: layouts.Item(n),
                                     label="Layouts.Item")
        _add_paper_circle(doc, radius)
        page_path = os.path.join(ctx["workdir"], "page_%s.pdf" % name)
        info = plotmod.plot_model_to_pdf(doc, page_path)
        pages.append({"layout": name, "path": page_path, "plot": info})
        if not info.get("ok"):
            ctx["notes"].append("布局 %s 出图失败：%r" % (name, info.get("warnings")))

    out = os.path.join(ctx["workdir"], "multipage.pdf")
    merge: Dict[str, Any] = {"ok": False, "error": None}
    try:
        from pypdf import PdfWriter
        writer = PdfWriter()
        for page in pages:
            if os.path.exists(page["path"]):
                writer.append(page["path"])
        with open(out, "wb") as fh:
            writer.write(fh)
        merge = {"ok": True, "pages": len(writer.pages),
                 "bytes": os.path.getsize(out), "error": None}
    except Exception as exc:                        # noqa: BLE001
        merge = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    ctx["artifacts"]["multipage"] = {"path": out, "pages": pages,
                                     "merge": merge}
    ctx["artifacts"]["pdf_path"] = out
