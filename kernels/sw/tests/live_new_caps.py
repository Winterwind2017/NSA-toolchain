"""真机试筋、焊件和窗口预览。已有打开的文档就退出，避免关掉别人的文件。"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from swkit.core.com import dispatch, pyw, val  # noqa: E402
from swkit.preview import capture_solidworks  # noqa: E402
from swkit.verified.features import extrude, new_part  # noqa: E402
from swkit.verified.rib import insert_rib  # noqa: E402
from swkit.verified.sketch_ops import create_sketch, line, rectangle  # noqa: E402
from swkit.verified.weldment import insert_weldment  # noqa: E402


def main() -> int:
    app = dispatch("SldWorks.Application")
    app.Visible = True
    # 上一轮试跑留下的未保存零件可以关掉。外面已经有人在用时不要进这个脚本。
    if os.environ.get("NSA_CLOSE_TEST_DOCS") == "1":
        app.CloseAllDocuments(True)
    doc = pyw().Dispatch(new_part())
    create_sketch(doc)
    rectangle(doc, 0, 0, 80, 40)
    extruded = extrude(doc, 10)
    create_sketch(doc, "上视基准面")
    line(doc, 0, 5, 80, 5)
    rib = insert_rib(doc, 4)
    weld_doc = pyw().Dispatch(new_part())
    weld = insert_weldment(weld_doc)
    shot = os.path.join(tempfile.gettempdir(), "nsa-sw-preview.bmp")
    preview = capture_solidworks(shot)
    report = {
        "revision": str(val(app, "RevisionNumber", "")),
        "extrude_ok": bool(extruded.get("ok")),
        "rib": rib,
        "weldment": weld,
        "preview_ok": bool(preview.get("ok")),
        "preview_bytes": preview.get("detail", {}).get("bytes"),
    }
    print(json.dumps(report, ensure_ascii=False, default=str))
    return 0 if rib.get("ok") and weld.get("ok") and preview.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
