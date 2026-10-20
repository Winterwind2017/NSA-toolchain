"""tests/draft_check.py —— 拔模分析：判据存在但入口拿不到（把证据固化成回归）

结论（实测，SW 2025 SP4.1）：

* `IPartingLineFeatureData` **有**可读判据：
  `DraftAnalysis(Angle)` + `GetFacesByTypeCount(Type)`（0 正 / 1 负 / 2 无拔模 / 3 跨面）
* 但拿不到这个对象：
  - `IFeatureManager.CreateDefinition(Type)` 的 `swFm`(132 项) 与 `swFeatureNameID`(8 项)
    里都**没有**分型线类型
  - `InsertMoldPartingLine(False/True)` 恒返回 **None**（选不选边都一样）
  - `InsertMoldPartingSurface(8 参)` 能建出「分型面1」，但曲面体数仍 0，且无 `GetDefinition`
* `IModelDoc2.MoldDraftAnalysis(Angle, Options, Colors, Shows)`（void，只着色）
  在 3 种 Colors 格式 × Shows 0–4 下**恒返回 False**，
  且面颜色 `GetMaterialPropertyValues2` 前后无变化

所以本项**不是"没找到判据"，而是"判据在、入口堵"**。等 SW 提供分型线特征创建路径
（或模具上下文）即可复用同一套判据。

    python tests/draft_check.py
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

from swkit.core.com import pyw, val                      # noqa: E402
from swkit.verified import features as F                 # noqa: E402
from swkit.verified import sketch_ops as S               # noqa: E402
from swkit.verified._common import bodies, faces_of      # noqa: E402
from swkit.verified.features import _select_all_edges    # noqa: E402


def _face_colors(doc):
    out = []
    for b in bodies(doc, 0) + bodies(doc, 1):
        for f in faces_of(b):
            try:
                c = val(f, "GetMaterialPropertyValues2", 0, True)
            except Exception:                       # noqa: BLE001
                c = None
            out.append(None if c is None else tuple(round(float(x), 3) for x in list(c)[:3]))
    return out


def main() -> int:
    app = pyw().Dispatch("SldWorks.Application")
    app.CloseAllDocuments(True)
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 80, 50)
    F.extrude(doc, 12.0, draft_deg=3.0)
    doc = pyw().Dispatch(app.ActiveDoc)

    sel = _select_all_edges(doc, 4)
    parting_line = doc.FeatureManager.InsertMoldPartingLine(False)
    parting_surf = doc.FeatureManager.InsertMoldPartingSurface(
        False, False, False, 0.0, 0.0, False, 0.0, True)
    surf_bodies = len(list(doc.GetBodies2(1, True) or []))

    before = _face_colors(doc)
    draft_results = []
    for shows in (0, 1, 4):
        try:
            r = doc.MoldDraftAnalysis(
                math.radians(1.0), 0,
                [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 1.0, 1.0, 0], shows)
        except Exception as exc:                # noqa: BLE001
            r = "ERR:%s" % str(exc)[:40]
        draft_results.append(r)
    after = _face_colors(doc)
    changed = sum(1 for a, b in zip(after, before) if a != b)

    detail = {
        "edges_selected": sel,
        "insert_mold_parting_line": parting_line is not None,
        "insert_mold_parting_surface": parting_surf is not None,
        "surface_bodies_after": surf_bodies,
        "mold_draft_analysis_returns": draft_results,
        "face_color_changes": changed,
        "faces": len(before),
        "note": "判据接口在 IPartingLineFeatureData，但分型线特征拿不到",
    }
    print(json.dumps(detail, ensure_ascii=False, indent=2))

    # 这些断言记录的是"当前事实"，一旦 SW 版本改变就会失败并提示重新评估
    checks = {
        "parting_line_unavailable": parting_line is None,
        "mold_draft_analysis_all_false": all(x is False for x in draft_results),
        "no_face_color_change": changed == 0,
    }
    print("checks:", checks)
    ok = all(checks.values())
    print("\n合计 1 项，通过 %d（结论：判据存在、入口堵）" % (1 if ok else 0))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
