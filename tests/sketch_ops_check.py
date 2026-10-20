"""tests/sketch_ops_check.py —— 草图实体族真机验收（14 条）

每个实体单独一个草图，判据统一是**活动草图的线段数增加**（矩形 +4、多边形 +N、
圆/椭圆/圆弧 +1、样条 +1）。偏移/图案需要先选中实体，脚本里显式选。

    python tests/sketch_ops_check.py [--part box_hole.SLDPRT]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)

from swkit.core.com import pyw                    # noqa: E402
from swkit.verified import sketch_ops as S        # noqa: E402

SIM = r"D:\bililive\acad_out\SW_ADV\sim"


def _open(app, src: str, name: str):
    dst = os.path.join(SIM, "check_" + name)
    if os.path.exists(dst):
        try:
            os.remove(dst)
        except OSError:
            pass
    shutil.copy2(src, dst)
    app.CloseAllDocuments(True)
    if app.OpenDoc(dst, 1) is None:
        raise RuntimeError("打不开：%s" % dst)
    return pyw().Dispatch(app.ActiveDoc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default=os.path.join(SIM, "box_hole.SLDPRT"))
    args = ap.parse_args()
    app = pyw().Dispatch("SldWorks.Application")
    results = {}

    def fresh(name):
        doc = _open(app, args.part, name)
        results.setdefault("_sketch", []).append(S.create_sketch(doc))
        return doc

    # 一个基准草图，逐个实体（每个新草图）
    doc = fresh("sk1.SLDPRT")
    results["line"] = S.line(doc, 0, 0, 50, 0)
    results["exit_0"] = S.exit_sketch(doc)

    doc = fresh("sk2.SLDPRT")
    results["circle"] = S.circle(doc, 10, 10, 8)

    doc = fresh("sk3.SLDPRT")
    results["rectangle"] = S.rectangle(doc, 0, 0, 40, 25)

    doc = fresh("sk4.SLDPRT")
    results["arc"] = S.arc(doc, 0, 0, 15, 0, 90)

    doc = fresh("sk5.SLDPRT")
    results["ellipse"] = S.ellipse(doc, 20, 10, 12, 6)

    doc = fresh("sk6.SLDPRT")
    results["polygon"] = S.polygon(doc, 0, 0, 6, 15)

    doc = fresh("sk7.SLDPRT")
    results["spline"] = S.spline(doc, [[0, 0], [15, 20], [35, 10], [50, 0]])

    doc = fresh("sk8.SLDPRT")
    results["centerline"] = S.centerline(doc, -20, 0, 20, 0)

    # circular_pattern 仍不可调（需 RadiusDim 尺寸对象）；offset/linear_pattern 已于 P2 转正。
    # 不能省），comtypes 又要求 CapEnds / XSpacingDim / RadiusDim 等尺寸对象参数。
    # 因此单列"已知不可验证"，不参与通过判定，但如实打印。
    known_unverified = {}
    doc = fresh("sk9.SLDPRT")
    S.rectangle(doc, 0, 0, 40, 25)
    results["offset"] = S.offset(doc, distance=3.0)

    doc = fresh("sk10.SLDPRT")
    S.rectangle(doc, 0, 0, 40, 25)
    results["linear_pattern"] = S.linear_pattern(
        doc, x_count=2, y_count=2, x_spacing=20.0, y_spacing=15.0)

    doc = fresh("sk11.SLDPRT")
    S.rectangle(doc, 0, 0, 40, 25)
    results["circular_pattern"] = S.circular_pattern(doc, count=4, radius=20.0)

    # edit_sketch：回到第一个草图再画一条线
    doc = _open(app, args.part, "sk12.SLDPRT")
    first = S.create_sketch(doc)
    results["_sketch"].append(first)
    S.line(doc, 0, 0, 30, 0)
    S.exit_sketch(doc)
    sk_name = None
    try:
        feats = doc.FeatureManager
        f = doc.FirstFeature
        while f is not None:
            if str(getattr(f, "GetTypeName2", "")) == "ProfileFeature":
                sk_name = f.Name
            f = f.GetNextFeature
    except Exception:
        pass
    if sk_name:
        results["edit_sketch"] = S.edit_sketch(doc, sk_name)
        S.exit_sketch(doc)

    for name, res in results.items():
        if name == "_sketch":
            continue
        print("== %-16s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("segments_before", "segments_after", "selected", "plane",
                         "active", "target", "error", "params")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:300])

    print()
    for name, res in known_unverified.items():
        print("-- %-16s (unverified/待解) ok=%s  %s"
              % (name, res.get("ok"), (res.get("detail") or {}).get("error", "")[:90]))

    sketches = results.pop("_sketch")
    base_ok = sum(1 for s in sketches if s.get("ok"))
    passed = sum(1 for v in results.values() if v.get("ok"))
    print("\n建草图 %d/%d 成功；实体类 %d 项通过 %d" % (base_ok, len(sketches),
                                                 len(results), passed))
    return 0 if (base_ok == len(sketches) and passed == len(results)) else 4


if __name__ == "__main__":
    raise SystemExit(main())
