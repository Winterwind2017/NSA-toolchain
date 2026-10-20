r"""tests/draft_read_check.py —— 拔模分析读取侧（需要已存在的分型线特征）

* 没有分型线时：必须**明确拒绝**（ok=False + 原因），不能假装成功
* 有分型线时：`DraftAnalysis` + `GetFacesByTypeCount(0..3)` 面数可读且和 > 0

分型线特征需要模具上下文，本仓库暂时只能"读取"不能"创建"，所以：
给了 `--part`（含分型线的零件）才做正例，否则只验证拒绝路径。

    python tests/draft_read_check.py
    python tests/draft_read_check.py --part "D:\path\with_parting_line.SLDPRT"
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)

from swkit.core.com import pyw                        # noqa: E402
from swkit.verified import draft as D                  # noqa: E402
from swkit.verified import features as F               # noqa: E402
from swkit.verified import sketch_ops as S             # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="", help="含分型线特征的零件（可选）")
    args = ap.parse_args()

    app = pyw().Dispatch("SldWorks.Application")
    results = {}

    if args.part and os.path.isfile(args.part):
        app.CloseAllDocuments(True)
        if app.OpenDoc(os.path.abspath(args.part), 1) is None:
            print("打不开：%s" % args.part)
            return 2
        doc = pyw().Dispatch(app.ActiveDoc)
        results["with_parting_line"] = D.analyze(doc, 1.0)
    else:
        app.CloseAllDocuments(True)
        doc = F.new_part()
        S.create_sketch(doc, "前视基准面")
        S.rectangle(doc, 0, 0, 80, 50)
        F.extrude(doc, 12.0)
        doc = pyw().Dispatch(app.ActiveDoc)
        results["no_parting_line"] = D.analyze(doc, 1.0)

    for name, res in results.items():
        print("== %-18s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        print("   " + json.dumps(res.get("detail"), ensure_ascii=False)[:320])

    if "no_parting_line" in results:
        # 拒绝路径：必须 ok=False 且给出原因
        r = results["no_parting_line"]
        ok = (r.get("ok") is False
              and bool((r.get("detail") or {}).get("error")))
        print("\n合计 1 项，通过 %d（拒绝路径）" % (1 if ok else 0))
        return 0 if ok else 4

    passed = sum(1 for v in results.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(results), passed))
    return 0 if passed == len(results) else 4


if __name__ == "__main__":
    raise SystemExit(main())
