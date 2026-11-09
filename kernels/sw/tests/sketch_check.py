"""tests/sketch_check.py —— 草图/文档级真机验收

覆盖：草图构造线、草图文字、草图约束、显示状态、材料库。

* 草图三项在**副本**上跑（会改模型）
* 显示状态：零件若没有显示状态，记为 SKIP（不是失败）——如实反映"没有可验对象"
* 材料库：不打开 SolidWorks，只解析 `.sldmat`

    python tests/sketch_check.py [--part box_hole.SLDPRT]
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

from swkit.core.com import pyw                       # noqa: E402
from swkit.verified import model as M                # noqa: E402
from swkit.verified import sketch as S               # noqa: E402

SIM = r"D:\bililive\acad_out\SW_ADV\sim"


def _open_copy(app, src: str, name: str):
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

    doc = _open_copy(app, args.part, "sk_a.SLDPRT")
    results["construction"] = S.construction(doc)

    doc = _open_copy(app, args.part, "sk_b.SLDPRT")
    results["sketch_text"] = S.sketch_text(doc, "swkit", 0.0, 0.0)

    doc = _open_copy(app, args.part, "sk_c.SLDPRT")
    results["sketch_constraint"] = S.sketch_constraint(doc, "sgHORIZONTAL")

    doc = _open_copy(app, args.part, "sk_d.SLDPRT")
    ds = M.activate_display_state(doc)
    results["activate_display_state"] = ds

    results["list_materials"] = M.list_materials()

    skipped = 0
    for name, res in results.items():
        detail = res.get("detail") or {}
        if res.get("ok") is False and detail.get("note"):
            skipped += 1
            print("== %-24s SKIP  %s" % (name, detail.get("note")))
            continue
        print("== %-24s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in detail.items()
                if k in ("before", "as_construction", "restored", "segments_before",
                         "segments_after", "text_readback", "constraints_before",
                         "constraints_after", "end_y_before", "end_y_after",
                         "categories", "materials", "files_total", "names",
                         "applied", "error", "note")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False)[:400])

    hard = [k for k, v in results.items()
            if not (v.get("ok") is False and (v.get("detail") or {}).get("note"))]
    passed = sum(1 for k in hard if results[k].get("ok"))
    print("\n合计 %d 项（另有 %d 项 SKIP），通过 %d" % (len(hard), skipped, passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
