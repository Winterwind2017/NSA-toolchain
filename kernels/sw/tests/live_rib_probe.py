"""试几种 InsertRib 参数。只在测试文档上跑。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from swkit.core.com import dispatch, pyw  # noqa: E402
from swkit.verified._common import com_doc, count_features  # noqa: E402
from swkit.verified.features import _volume_mm3, extrude, new_part  # noqa: E402
from swkit.verified.sketch_ops import create_sketch, line  # noqa: E402


def main() -> None:
    app = dispatch("SldWorks.Application")
    app.Visible = True
    if os.environ.get("NSA_CLOSE_TEST_DOCS") == "1":
        app.CloseAllDocuments(True)
    doc = pyw().Dispatch(new_part())
    create_sketch(doc)
    from swkit.verified.sketch_ops import rectangle
    rectangle(doc, 0, 0, 80, 40)
    print("extrude", extrude(doc, 10).get("ok"), "V", _volume_mm3(doc))
    trials = []
    for norm in (False, True):
        for two in (False, True):
            create_sketch(doc, "前视基准面")
            line(doc, 10, 10, 70, 30)
            before = count_features(doc)
            _sw, md = com_doc()
            returned = md.FeatureManager.InsertRib(
                two, False, 0.004, 0, False, False, False, 0.0, norm, False)
            after = count_features(doc)
            volume = _volume_mm3(doc)
            trials.append({
                "norm": norm, "two": two, "returned": str(returned),
                "features": [before, after], "volume": volume,
            })
            print(trials[-1])
            if after > before:
                return
            try:
                doc.EditUndo2(1)
            except Exception as exc:  # noqa: BLE001
                print("undo", exc)
    print("none worked")


if __name__ == "__main__":
    main()
