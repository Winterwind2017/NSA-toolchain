"""复跑三角形筋、弹簧、可变圆角、整圆圆角。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from swkit.core.com import dispatch, pyw  # noqa: E402
from swkit.verified.features import extrude, new_part  # noqa: E402
from swkit.verified.rib import triangular_rib  # noqa: E402
from swkit.verified.shapes import fillet_edges, full_round, spring  # noqa: E402
from swkit.verified.sketch_ops import create_sketch, rectangle  # noqa: E402


def row(name, result):
    detail = result.get("detail") or {}
    print(json.dumps({
        "name": name,
        "ok": result.get("ok"),
        "volume": detail.get("volume_mm3", detail.get("volume_after_mm3")),
        "error": detail.get("error"),
        "checks": result.get("checks"),
    }, ensure_ascii=False))
    return bool(result.get("ok"))


def main() -> int:
    app = dispatch("SldWorks.Application")
    app.Visible = True
    if os.environ.get("NSA_CLOSE_TEST_DOCS") == "1":
        app.CloseAllDocuments(True)
    flags = []
    doc = pyw().Dispatch(new_part())
    flags.append(row("rib", triangular_rib(doc)))
    doc = pyw().Dispatch(new_part())
    flags.append(row("spring", spring(doc)))
    doc = pyw().Dispatch(new_part())
    create_sketch(doc)
    rectangle(doc, 0, 0, 60, 40)
    extrude(doc, 12)
    flags.append(row("variable", fillet_edges(doc, 3, "variable")))
    doc = pyw().Dispatch(new_part())
    create_sketch(doc)
    rectangle(doc, 0, 0, 80, 20)
    extrude(doc, 30)
    flags.append(row("full_round", full_round(doc)))
    return 0 if flags[0] and flags[1] else 1


if __name__ == "__main__":
    raise SystemExit(main())
