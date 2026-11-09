"""tests/part_check.py —— 零件/特征侧真机验收

对 `swkit.verified.part` 的每个函数跑一次真机，打印证据字典并给总判定。

用**副本**跑（shell / pattern / split_line 会改模型），原始测试件不动。

    python tests/part_check.py [--part box_hole.SLDPRT] [--surface reg_surf.SLDPRT]
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
from swkit.verified import part as P              # noqa: E402

SIM = r"D:\bililive\acad_out\SW_ADV\sim"


def _app():
    return pyw().Dispatch("SldWorks.Application")


def _open_copy(app, src: str, name: str) -> str:
    dst = os.path.join(SIM, "check_" + name)
    if os.path.exists(dst):
        try:
            os.remove(dst)
        except OSError:
            pass
    shutil.copy2(src, dst)
    app.CloseAllDocuments(True)
    doc = app.OpenDoc(dst, 1)
    if doc is None:
        raise RuntimeError("打不开：%s" % dst)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default=os.path.join(SIM, "box_hole.SLDPRT"))
    ap.add_argument("--surface", default=os.path.join(SIM, "reg_surf.SLDPRT"))
    args = ap.parse_args()

    app = _app()
    results = {}

    # 1) 只读：包围盒 + 截图
    _open_copy(app, args.part, "part_a.SLDPRT")
    doc = pyw().Dispatch(app.ActiveDoc)
    results["bounding_box"] = P.bounding_box(doc)
    shot = os.path.join(SIM, "check_shot.bmp")
    results["screenshot"] = P.screenshot(doc, shot, 1200, 800)

    # 2) 抽壳
    _open_copy(app, args.part, "part_b.SLDPRT")
    doc = pyw().Dispatch(app.ActiveDoc)
    results["shell"] = P.shell(doc, 0.002)

    # 3) 特征线性阵列
    _open_copy(app, args.part, "part_c.SLDPRT")
    doc = pyw().Dispatch(app.ActiveDoc)
    results["pattern_feature"] = P.pattern_feature(doc, kind="linear",
                                                  count=3, spacing=0.02)

    # 3b) 特征圆形阵列
    _open_copy(app, args.part, "part_e.SLDPRT")
    doc = pyw().Dispatch(app.ActiveDoc)
    results["pattern_circular"] = P.pattern_feature(doc, kind="circular",
                                                    count=3, angle_deg=120)

    # 4) 分割线
    _open_copy(app, args.part, "part_d.SLDPRT")
    doc = pyw().Dispatch(app.ActiveDoc)
    results["split_line"] = P.split_line(doc)

    # 5) 曲面加厚 / 偏移（需要曲面件）
    if os.path.exists(args.surface):
        _open_copy(app, args.surface, "surf_a.SLDPRT")
        doc = pyw().Dispatch(app.ActiveDoc)
        results["offset_surface"] = P.offset_surface(doc, 0.002)
        _open_copy(app, args.surface, "surf_b.SLDPRT")
        doc = pyw().Dispatch(app.ActiveDoc)
        results["thicken_surface"] = P.thicken_surface(doc, 0.002)
    else:
        results["surface"] = {"ok": None, "skipped": "找不到曲面测试件：%s" % args.surface}

    for name, res in results.items():
        print("== %-18s ok=%s  checks=%s"
              % (name, res.get("ok"), res.get("checks")))
        det = res.get("detail") or {}
        keep = {k: v for k, v in det.items() if k in
                ("boxes", "bytes", "before", "after", "features_before",
                 "features_after", "surfaces_before", "surfaces_after",
                 "path", "attempts", "error", "target", "longest_edge_mm")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False)[:420])

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
