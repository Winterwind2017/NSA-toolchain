"""tests/config_io_check.py —— 文档开关 / 另存副本 / 配置 / 引用文档

9 项：
1. open_document（文档数 +1）
2. list_configurations（配置数 > 0）
3. add_configuration（+1）
4. activate_configuration（激活名读回）
5. save_as_copy（新文件出现、原路径不变）
6. save_all（无异常、文档数不变）
7. get_referenced_documents（图纸 → 模型）
8. close_document（-1）
9. close_all（→0）

    python tests/config_io_check.py
"""

from __future__ import annotations

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
from swkit.verified import config_io as C            # noqa: E402
from swkit.verified import drawing as D              # noqa: E402

SIM = r"D:\bililive\acad_out\SW_ADV\sim"
OUT = os.path.join(os.path.expanduser("~"), ".swkit", "export")
PART = os.path.join(SIM, "box_hole.SLDPRT")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    app = pyw().Dispatch("SldWorks.Application")
    app.CloseAllDocuments(True)
    results = {}

    results["open"] = C.open_document(PART)
    doc = pyw().Dispatch(app.ActiveDoc)
    results["configs"] = C.list_configurations(doc)
    results["add_cfg"] = C.add_configuration(doc, "CFG_SWKIT")
    results["activate"] = C.activate_configuration(doc, "CFG_SWKIT")
    results["save_copy"] = C.save_as_copy(
        doc, os.path.join(OUT, "copy_of_box.SLDPRT"))
    results["save_all"] = C.save_all()

    # 图纸 → 引用文档
    drw = D.new_drawing(PART)
    drw_doc = pyw().Dispatch(app.ActiveDoc)
    results["refs"] = C.get_referenced_documents(drw_doc)
    results["close_one"] = C.close_document()
    results["close_all"] = C.close_all(True)

    for name, res in results.items():
        print("== %-11s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("documents_before", "documents_after", "count", "names",
                         "active", "configurations_before", "configurations_after",
                         "bytes", "api_used", "original_path", "path_after",
                         "documents", "title", "returned", "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:300])

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
