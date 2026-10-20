"""tests/flange_probe_check.py —— 边法兰"能建特征、不能建几何"的证据固化

断言（SW 2025 SP4.1 实测）：

1. `InsertSketchForEdgeFlange` 生成的轮廓草图是**空的**（0 段 0 点）
2. 用该草图调 `InsertSheetMetalEdgeFlange` 会得到 `EdgeFlange` 特征
3. 但体积/面数/边数**完全不变**（零几何）
4. 特征数据的 `GetEdgeCount` 却是 1（数据合法、几何为零）

一旦 SW 版本修好，第 1/3 条会失败 → 提醒重新评估（见 docs/SHEET_METAL_NOTES.md）。

    python tests/flange_probe_check.py
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)

from swkit.core.com import pyw, val, none_dispatch                  # noqa: E402
from swkit.verified import features as F                             # noqa: E402
from swkit.verified import inspect as I                              # noqa: E402
from swkit.verified import sheet_metal as SM                         # noqa: E402
from swkit.verified import sketch_ops as S                           # noqa: E402
from swkit.verified._common import bodies, faces_of                  # noqa: E402


def _vol(doc):
    v = (I.mass_properties(doc).get("detail") or {}).get("volume_m3")
    return None if v is None else round(v * 1e9, 3)


def _pick_edge(doc):
    for b in bodies(doc, 0):
        for f in faces_of(b):
            for e in (val(f, "GetEdges") or []):
                try:
                    c = e.GetCurve()
                    if c is not None and c.IsCircle():
                        continue
                except Exception:            # noqa: BLE001
                    pass
                return e
    return None


def main() -> int:
    app = pyw().Dispatch("SldWorks.Application")
    app.CloseAllDocuments(True)
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 60, 40)
    SM.base_flange(doc, 2.0, 2.0, 30.0)
    doc = pyw().Dispatch(app.ActiveDoc)

    edge = _pick_edge(doc)
    if edge is None:
        print("没有可用边")
        return 2
    v0 = _vol(doc)
    c0 = F.shape_counts(doc)

    doc.ClearSelection2(True)
    edge.Select2(False, 1)
    sketch_feat = doc.InsertSketchForEdgeFlange(edge, math.radians(90), False)
    doc = pyw().Dispatch(app.ActiveDoc)

    segs = None
    if sketch_feat is not None:
        sk = val(sketch_feat, "GetSpecificFeature2")
        if sk is not None:
            segs = len(list(val(sk, "GetSketchSegments") or []))

    feat = doc.InsertSheetMetalEdgeFlange(edge, sketch_feat, 0, math.radians(90),
                                          0.002, 0, 0.0, 0, 0.5, 0.001, 0.001)
    try:
        doc.EditRebuild3()
    except Exception:                        # noqa: BLE001
        pass
    doc = pyw().Dispatch(app.ActiveDoc)
    v1 = _vol(doc)
    c1 = F.shape_counts(doc)

    detail = {
        "profile_sketch_segments": segs,
        "edgeflange_created": feat is not None,
        "volume_before": v0, "volume_after": v1,
        "faces_before": c0["faces"], "faces_after": c1["faces"],
        "edges_before": c0["edges"], "edges_after": c1["edges"],
    }
    print(json.dumps(detail, ensure_ascii=False, indent=2))

    checks = {
        "profile_sketch_empty": segs == 0,
        "feature_created": feat is not None,
        "geometry_unchanged": (v0 == v1 and c0["faces"] == c1["faces"]
                               and c0["edges"] == c1["edges"]),
    }
    print("checks:", checks)
    ok = all(checks.values())
    print("\n合计 1 项，通过 %d（结论：能建特征、不能建几何）" % (1 if ok else 0))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
