"""`plot.style` 的判据：样式表读回 + **像素级墨量比**。

为什么不用"返回值/设置成功"当判据：`layout.StyleSheet = 'x.ctb'` 不抛异常
也不代表出图真的按线宽走。这里直接把两张 PDF 渲染成灰度图数墨量——
线宽 1.00mm 出的图应当明显比 0.13mm 的"重"。

墨量定义：渲染后灰度值 < 200 的像素占比。取 60dpi + 每 4 字节采样，
A3 一张约 30 万样本，够区分 1.00mm 与默认线宽（实测比值 > 2），也够快。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .base import Readback, close, verdict


def ink_ratio(path: str, *, dpi: int = 60, dark: int = 200,
              stride: int = 4) -> Optional[float]:
    """PDF 第一页的墨量占比（0–1）；读不了返回 None（判据会因此失败，不猜）。"""
    try:
        import fitz                                    # PyMuPDF
    except Exception:                                  # noqa: BLE001
        return None
    if not (os.path.isfile(path) and os.path.getsize(path) > 0):
        return None
    try:
        doc = fitz.open(path)
        if doc.page_count < 1:
            return None
        pix = doc[0].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        data = pix.samples
    except Exception:                                  # noqa: BLE001
        return None
    if not data:
        return None
    sample = data[::stride]
    dark_n = sum(1 for b in sample if b < dark)
    return dark_n / float(len(sample))


def judge_plot_style(rb: Readback, *, info: Dict[str, Any],
                     expect_table: Optional[str] = None,
                     rel_increase: float = 1.2,
                     min_bytes: int = 2000) -> Dict[str, Any]:
    """三张 PDF + 两个图层线宽的读回。

    判据（全部要能反驳）：
      files        三张 PDF 都存在且 ≥ min_bytes
      style_sheet  layout.StyleSheet 读回 == 请求的表名（表名非空）
      lineweights  两个图层的 Lineweight 读回 == 请求值（100 / 13）
      ink_on_gt_off 有线宽版墨量 > 无线宽版 × rel_increase
      ink_present   三张图都有墨（不是空白页）
    """
    info = info or {}
    paths = info.get("paths") or {}
    layers = info.get("layers") or {}
    want_lw = info.get("lineweights") or {}
    applied = info.get("style_table") or {}

    sizes = {k: (os.path.getsize(v) if v and os.path.isfile(v) else 0)
             for k, v in paths.items()}
    ink = {k: ink_ratio(v) for k, v in paths.items()}

    ink_on = ink.get("lineweight_on")
    ink_off = ink.get("lineweight_off")
    ratio = (ink_on / ink_off) if (ink_on and ink_off) else None

    lw_ok = (int(layers.get("thick", {}).get("lineweight", -1)) == int(want_lw.get("thick", -100))
             and int(layers.get("thin", {}).get("lineweight", -1)) == int(want_lw.get("thin", -200)))

    table_readback = str(applied.get("readback") or "")
    want_table = str(expect_table or applied.get("requested") or "")
    style_ok = bool(want_table) and table_readback == want_table

    checks = {
        "files": all(s >= min_bytes for s in sizes.values()) and len(paths) == 3,
        "style_sheet": style_ok,
        "lineweights": lw_ok,
        "ink_present": all((v or 0) > 0.0005 for v in ink.values()),
        "ink_on_gt_off": bool(ratio is not None and ratio >= rel_increase),
    }

    detail: Dict[str, Any] = {
        "paths": dict(paths),
        "bytes": sizes,
        "ink": {k: (round(v, 6) if v is not None else None) for k, v in ink.items()},
        "ink_ratio_on_over_off": (round(ratio, 3) if ratio is not None else None),
        "ink_ratio_required": rel_increase,
        "style_table_requested": want_table or None,
        "style_table_readback": table_readback or None,
        "style_table_error": applied.get("error"),
        "style_tables_seen": (info.get("style_tables_seen") or [])[:8],
        "lineweights_wanted": want_lw,
        "lineweights_readback": {
            "thick": (layers.get("thick") or {}).get("lineweight"),
            "thin": (layers.get("thin") or {}).get("lineweight"),
        },
        "readback_after": info.get("readback"),
        "unit_note": "线宽单位 1/100 mm（100 = 1.00mm，13 = 0.13mm）",
    }
    return verdict(checks, detail, {"plot_style_info": {
        k: v for k, v in info.items() if k != "plot"}})
