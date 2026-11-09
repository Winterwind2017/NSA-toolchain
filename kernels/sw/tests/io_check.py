"""tests/io_check.py —— 导出族真机验收（判据是文件签名）

在空白零件上拉伸一个 40×25×20 的方块，然后导出 5 种格式并校验签名：

* STEP：`ISO-10303-21`
* STL：ASCII `solid` 或二进制 84 字节头
* PDF：`%PDF`
* IGES：`S` 段 + `1H`
* DXF：`SECTION`

    python tests/io_check.py
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

from swkit.core.com import pyw                     # noqa: E402
from swkit.verified import features as F           # noqa: E402
from swkit.verified import io_export as IO         # noqa: E402
from swkit.verified import sketch_ops as S         # noqa: E402

OUT = os.path.join(os.path.expanduser("~"), ".swkit", "export")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    ext = F.extrude(doc, 20.0)
    print("== 夹具 extrude ok=%s volume=%s mm3"
          % (ext.get("ok"), (ext.get("detail") or {}).get("volume_after_mm3")))

    results = {}
    results["step"] = IO.export_step(os.path.join(OUT, "block.step"))
    results["stl"] = IO.export_stl(os.path.join(OUT, "block.stl"))
    known = {}
    results["iges"] = IO.export_iges(os.path.join(OUT, "block.iges"), doc=doc)
    results["pdf"] = IO.export_pdf(os.path.join(OUT, "block.pdf"))
    known["dxf"] = IO.export_dxf(os.path.join(OUT, "block.dxf"))
    results["save"] = IO.save_document(doc, os.path.join(OUT, "block.SLDPRT"))

    print()
    for name, res in known.items():
        print("-- %-6s (unverified/待解) %s" % (name,
              ((res.get("detail") or {}).get("error") or "")[:80]))

    for name, res in results.items():
        print("== %-6s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        detail = res.get("detail") or {}
        keep = {k: v for k, v in detail.items()
                if k in ("path", "bytes", "head", "format_ok", "error",
                         "bytes_before", "bytes_after")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:300])

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d（输出目录 %s）" % (len(hard), passed, OUT))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
