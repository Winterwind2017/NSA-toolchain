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
    config = profile_configurations(app, found["path"])[0]
    doc = pyw().Dispatch(new_part())
    create_sketch(doc)
    line(doc, 0, 0, 300, 0)
    exit_sketch(doc)
    result = structural_member(doc, found["path"], config)
    print(json.dumps({
        "config": config,
        "ok": result.get("ok"),
        "checks": result.get("checks"),
        "new_types": result.get("detail", {}).get("new_types"),
        "volume": result.get("detail", {}).get("volume_mm3"),
        "config_error": result.get("detail", {}).get("configuration_error"),
        "error": result.get("detail", {}).get("error"),
    }, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
