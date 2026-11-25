"""两条边两个半径，以及一组整圆圆角选面标记。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from swkit.core.com import dispatch, pyw  # noqa: E402
from swkit.verified._common import com_doc  # noqa: E402
from swkit.verified.features import _volume_mm3, extrude, new_part  # noqa: E402
from swkit.verified.shapes import fillet_two_radii, full_round  # noqa: E402
from swkit.verified.sketch_ops import create_sketch, rectangle  # noqa: E402


def plate(x, y, z):
    doc = pyw().Dispatch(new_part())
    create_sketch(doc)
    rectangle(doc, 0, 0, x, y)
    extrude(doc, z)
    return doc


def main() -> int:
    app = dispatch("SldWorks.Application")
    app.Visible = True
    if os.environ.get("NSA_CLOSE_TEST_DOCS") == "1":
        app.CloseAllDocuments(True)
    made = fillet_two_radii(plate(60, 40, 12), 2, 5)
    print("two", made.get("ok"), made.get("checks"))
    doc = plate(80, 20, 30)
    print("full_default", full_round(doc).get("ok"), _volume_mm3(doc))
    _sw, md = com_doc()
    bodies = list(doc.GetBodies2(0, True) or [])
    faces = []
    for body in bodies:
        raw = body.GetFaces
        faces.extend(list(raw if not callable(raw) else raw() or []))

    def center(face):
        raw = face.GetBox
        box = raw if not callable(raw) else raw()
        return tuple((box[i] + box[i + 3]) / 2.0 for i in range(3))

    left = min(faces, key=lambda face: center(face)[0])
    right = max(faces, key=lambda face: center(face)[0])
    top = max(faces, key=lambda face: center(face)[1])
    for marks in ((1, 2, 4), (2, 4, 8), (4, 8, 16)):
        before = _volume_mm3(doc)
        doc.ClearSelection2(True)
        left.Select2(False, marks[0])
        top.Select2(True, marks[1])
        right.Select2(True, marks[2])
        try:
            md.FeatureManager.FeatureFillet3(
                2, 0.0, 0.0, 0.0, 3, 0, 0, None, None, None, None, None, None, None)
            print("marks", marks, before, _volume_mm3(doc))
        except Exception as exc:  # noqa: BLE001
            print("marks", marks, type(exc).__name__, exc)
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
