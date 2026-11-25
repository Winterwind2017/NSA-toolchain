"""用选中的草图线段放一根 ISO 方管。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from swkit.core.com import dispatch, pyw  # noqa: E402
from swkit.verified.features import new_part  # noqa: E402
from swkit.verified.sketch_ops import create_sketch, exit_sketch, line  # noqa: E402
from swkit.verified.weldment import profile_configurations, structural_member  # noqa: E402
from swkit.weldment_library import default_profile  # noqa: E402


def main() -> int:
    found = default_profile()
    if not found:
        print("no profile")
        return 2
    app = dispatch("SldWorks.Application")
    app.Visible = True
    if os.environ.get("NSA_CLOSE_TEST_DOCS") == "1":
        app.CloseAllDocuments(True)
    names = profile_configurations(app, found["path"])
    rows = []
    for config in (names[0], "40 x 40 x 4", "99 x 99 x 9"):
        doc = pyw().Dispatch(new_part())
        create_sketch(doc)
        line(doc, 0, 0, 300, 0)
        exit_sketch(doc)
        result = structural_member(doc, found["path"], config)
        rows.append({
            "config": config,
            "ok": result.get("ok"),
            "readback": result.get("detail", {}).get("configuration_readback"),
            "volume": result.get("detail", {}).get("volume_mm3"),
            "error": result.get("detail", {}).get("configuration_error"),
        })
        print(json.dumps(rows[-1], ensure_ascii=False))
    small = rows[0]["volume"] or 0
    large = rows[1]["volume"] or 0
    good = rows[0]["ok"] and rows[1]["ok"] and large > small * 2 and rows[2]["ok"] is False
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
