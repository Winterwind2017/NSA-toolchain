#!/usr/bin/env python3
"""离线出图：零件 → 三视图线框 + 图框 + 标题栏 → 矢量 PDF。

    python tools/drawing.py --part flange --outer 120 --bore 40 --thickness 10 \
        --title 法兰盘 --number NSA-001 --material Q235B --sheet A3 --pdf flange.pdf

判据（打印在末尾，也可 --json）：PDF 头、单页、幅面、标题栏文字可提取、
可见/隐藏线框段数、比例是否落在标准序列。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from acadkit.brep import drawing as D          # noqa: E402
from acadkit.brep import parts as B            # noqa: E402
from acadkit.brep.parts import BrepError       # noqa: E402

PARTS = ("plate", "shaft", "flange", "stepped", "bracket")


def _make(args):
    if args.part == "plate":
        return B.plate(length=args.length, width=args.width, thickness=args.thickness)
    if args.part == "shaft":
        return B.shaft(diameter=args.diameter, length=args.length)
    if args.part == "flange":
        return B.flange(outer_d=args.outer, bore_d=args.bore, thickness=args.thickness,
                        bolt_holes=[{"diameter": 10, "bcd": args.bcd or args.bore * 1.6,
                                     "count": args.bolt_count}])
    if args.part == "stepped":
        raw = [x.strip() for x in args.segments.split(",") if x.strip()]
        if not raw:
            raise BrepError("stepped 需要 --segments，如 20x60,12x40")
        segs = []
        for tok in raw:
            d_s, L_s = tok.lower().split("x")
            segs.append((float(d_s), float(L_s)))
        return B.stepped_shaft(segs)
    if args.part == "bracket":
        return B.bracket(length=args.length, root_height=args.root_h,
                         tip_height=args.tip_h, width=args.width)
    raise BrepError("未知零件：%s（可用：%s）" % (args.part, ", ".join(PARTS)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="离线出图（三视图 + 图框 + 标题栏 → PDF）")
    ap.add_argument("--part", default="plate", choices=PARTS)
    ap.add_argument("--pdf", default="", help="输出 PDF 路径（默认放临时目录）")
    ap.add_argument("--sheet", default="A3", choices=tuple(D.SHEETS))
    ap.add_argument("--views", default="front,top,right",
                    help="逗号分隔；可用 front/top/right/iso")
    ap.add_argument("--title", default="", help="标题栏：图名")
    ap.add_argument("--number", default="", help="标题栏：图号")
    ap.add_argument("--material", default="", help="标题栏：材料")
    ap.add_argument("--scale", default="", help="标题栏：比例（留空=自动标准比例）")
    ap.add_argument("--company", default="nsa-toolchain", help="标题栏：单位")
    ap.add_argument("--length", type=float, default=120.0)
    ap.add_argument("--width", type=float, default=80.0)
    ap.add_argument("--thickness", type=float, default=10.0)
    ap.add_argument("--diameter", type=float, default=40.0)
    ap.add_argument("--outer", type=float, default=120.0)
    ap.add_argument("--bore", type=float, default=40.0)
    ap.add_argument("--bolt-count", type=int, default=4)
    ap.add_argument("--bcd", type=float, default=0.0)
    ap.add_argument("--root-h", type=float, default=30.0)
    ap.add_argument("--tip-h", type=float, default=10.0)
    ap.add_argument("--segments", default="")
    ap.add_argument("--max-scale", type=float, default=1.0,
                    help="自动比例的放大上限（1.0 = 不放大）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    views = [v.strip() for v in args.views.split(",") if v.strip()]
    pdf = args.pdf or os.path.join(
        os.environ.get("TEMP", "/tmp"), "nsa_drawing_%s_%s.pdf" % (args.part, args.sheet))

    try:
        part = _make(args)
        stats = D.sheet_pdf(
            part, pdf, sheet=args.sheet, views=views, max_scale=args.max_scale,
            title_block={"title": args.title, "number": args.number,
                         "material": args.material, "scale": args.scale,
                         "company": args.company})
    except (BrepError, ValueError) as exc:
        print("出图失败：%s" % exc, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))
    else:
        print("PDF    ：%s（%d B）" % (stats["path"], stats["bytes"]))
        print("图幅   ：%s  %.0f×%.0f mm   比例 %s"
              % (stats["sheet"], stats["page_mm"][0], stats["page_mm"][1],
                 stats["scale_label"]))
        print("线框   ：可见 %d 段，隐藏 %d 段（%s）"
              % (stats["segments_visible"], stats["segments_hidden"],
                 "、".join(stats["views"])))
        print("页数   ：%s   幅面复核：%s   文字可提取：%s（缺失：%s）"
              % (stats.get("pages"), "过" if stats.get("page_size_ok") else "未过",
                 "是" if stats.get("text_extractable") else "否",
                 stats.get("missing_text") or "无"))
        print("字体   ：%s%s" % (stats["font"] or "（无中文字体，标签用英文）",
                                "" if stats["chinese_labels"] else "  ← 已退回英文"))

    ok = bool(stats.get("page_size_ok")) and bool(stats.get("text_ok")) \
        and stats["pages"] == 1 and stats["segments_visible"] > 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
