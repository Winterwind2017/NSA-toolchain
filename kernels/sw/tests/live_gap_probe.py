"""齿轮、链轮、可变圆角、筋，各做一次。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from swkit.core.com import dispatch, pyw  # noqa: E402
from swkit.verified.features import extrude, new_part  # noqa: E402
from swkit.verified.rib import insert_rib  # noqa: E402
from swkit.verified.shapes import fillet_edges, gear, sprocket  # noqa: E402
from swkit.verified.sketch_ops import create_sketch, line, rectangle  # noqa: E402


def main() -> int:
    app = dispatch("SldWorks.Application")
    app.Visible = True
    if os.environ.get("NSA_CLOSE_TEST_DOCS") == "1":
        app.CloseAllDocuments(True)
    rows = []
    doc = pyw().Dispatch(new_part())
    made = gear(doc, module=2, teeth=12, thickness_mm=8)
    rows.append(("gear", made.get("ok"), made.get("detail", {}).get("volume_mm3"), made.get("detail", {}).get("error")))
    doc = pyw().Dispatch(new_part())
    made = sprocket(doc)
    rows.append(("sprocket", made.get("ok"), made.get("detail", {}).get("volume_mm3"), made.get("detail", {}).get("error")))
    doc = pyw().Dispatch(new_part())
    create_sketch(doc)
    rectangle(doc, 0, 0, 60, 40)
    extrude(doc, 12)
    made = fillet_edges(doc, 2, "variable")
    rows.append(("fillet", made.get("ok"), made.get("detail", {}).get("volume_after_mm3"), made.get("detail", {}).get("error")))
    create_sketch(doc, "上视基准面")
    line(doc, -10, 6, 70, 6)
    made = insert_rib(doc, 3)
    rows.append(("rib", made.get("ok"), made.get("detail", {}).get("volume_after_mm3"), made.get("detail", {}).get("error") or made.get("detail", {}).get("returned_type")))
    for row in rows:
        print(json.dumps({"name": row[0], "ok": row[1], "volume": row[2], "note": row[3]}, ensure_ascii=False))
    return 0 if rows[0][1] and rows[1][1] else 1


if __name__ == "__main__":
    raise SystemExit(main())
