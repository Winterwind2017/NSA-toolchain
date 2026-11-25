"""80×20×30 的板，整圆圆角后体积必须下降。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from swkit.core.com import dispatch, pyw  # noqa: E402
from swkit.verified.features import extrude, new_part  # noqa: E402
from swkit.verified.shapes import full_round  # noqa: E402
from swkit.verified.sketch_ops import create_sketch, rectangle  # noqa: E402


def main() -> int:
    app = dispatch("SldWorks.Application")
    app.Visible = True
    if os.environ.get("NSA_CLOSE_TEST_DOCS") == "1":
        app.CloseAllDocuments(True)
    doc = pyw().Dispatch(new_part())
    create_sketch(doc)
    rectangle(doc, 0, 0, 80, 20)
    extrude(doc, 30)
    made = full_round(doc)
    print(made.get("ok"), made.get("checks"), made.get("detail"))
    return 0 if made.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
