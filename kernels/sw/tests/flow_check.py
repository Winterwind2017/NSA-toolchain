"""tests/flow_check.py —— Flow Simulation API 自检 / 建工程

判据：
1. `status`：版本串非空、工程数可读、拿到 Flow 侧文档与 CAD 文档对象
2. 负面对照：SolidWorks 里没有文档时，`GetActiveDoc` 为 None → ok=False 并给出原因
3. `create_project`：返回 `IProject` 对象

    python tests/flow_check.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)

from swkit.core.com import pyw                          # noqa: E402
from swkit.verified import features as F                # noqa: E402
from swkit.verified import flow as FL                   # noqa: E402
from swkit.verified import sketch_ops as S              # noqa: E402


def main() -> int:
    from swkit.verified import flow as _FL
    _probe = _FL.status()
    if (_probe.get("detail") or {}).get("addin_loaded") is False:
        print("SKIP：Flow Simulation 插件未在当前 SolidWorks 会话中加载")
        print("      " + str((_probe.get("detail") or {}).get("error"))[:160])
        print("\n合计 0 项（SKIP），通过 0 —— 环境前置条件不满足，不算回归")
        return 0

    if not FL.available():
        print("Flow Simulation 未安装，跳过")
        return 0

    sw = pyw().Dispatch("SldWorks.Application")

    # 负面对照：无文档
    sw.CloseAllDocuments(True)
    no_doc = FL.status()

    # 正例：开一个零件
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 80, 50)
    F.extrude(doc, 12.0)
    ok_res = FL.status()
    proj = FL.create_project()

    results = {"no_document": no_doc, "with_document": ok_res, "create_project": proj}
    for name, res in results.items():
        print("== %-14s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        print("   " + json.dumps(res.get("detail"), ensure_ascii=False)[:330])

    # 可区分性：无文档必须 False，且原因明确
    diff_ok = (no_doc.get("ok") is False
               and "error" in (no_doc.get("detail") or {})
               and ok_res.get("ok") is True)

    passed = sum(1 for k, v in results.items() if k != "no_document" and v.get("ok"))
    total = 2
    print("\n可区分性: %s" % diff_ok)
    print("合计 %d 项，通过 %d（可区分性 %s）" % (total, passed, diff_ok))
    return 0 if (passed == total and diff_ok) else 4


if __name__ == "__main__":
    raise SystemExit(main())
