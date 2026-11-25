"""在图纸上写公共基准和投影公差带高度，并再试一次整圆圆角的相邻面。"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from swkit.core.com import dispatch, none_dispatch, pyw, val  # noqa: E402
from swkit.verified._common import com_doc  # noqa: E402
from swkit.verified.drawing import first_model_view, new_drawing  # noqa: E402
from swkit.verified.features import _volume_mm3, extrude, new_part  # noqa: E402
from swkit.verified.gtol_frame import set_projected_zone  # noqa: E402
from swkit.verified.sketch_ops import create_sketch, rectangle  # noqa: E402


def main() -> int:
    app = dispatch("SldWorks.Application")
    app.Visible = True
    if os.environ.get("NSA_CLOSE_TEST_DOCS") == "1":
        app.CloseAllDocuments(True)
    doc = pyw().Dispatch(new_part())
    create_sketch(doc)
    rectangle(doc, 0, 0, 40, 20)
    extrude(doc, 10)
    part = os.path.join(tempfile.gettempdir(), "nsa-gtol-part.sldprt")
    doc.SaveAs3(part, 0, 1)
    drawing = new_drawing(part)
    print("drawing", drawing.get("ok"), drawing.get("detail"))
    draw = pyw().Dispatch(app.ActiveDoc)
    from swkit.verified import drawing as drawing_mod
    view = first_model_view(draw)
    edges = drawing_mod._view_edges(view) if view is not None else []
    print("edges", len(edges))
    _sw, md = com_doc()
    target = None
    for edge in edges[:6]:
        try:
            edge.Select4(False, none_dispatch())
            target = md.InsertGtol()
        except Exception as exc:  # noqa: BLE001
            print("insert", type(exc).__name__, exc)
            continue
        if target is not None:
            break
    print("gtol", target is not None)
    if target is not None:
        made = set_projected_zone(target, "A-B", 12)
        print("zone", made.get("ok"), made.get("checks"), made.get("detail"))
    return 0 if target is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
